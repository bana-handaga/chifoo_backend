"""
build_kolaboasi_graph.py
────────────────────────
Membangun jaringan kerjasama antar peneliti PTMA (co-authorship network)
dari tabel SintaPenelitianAuthor, SintaPengabdianAuthor, dan SintaScopusArtikelAuthor.

Menggunakan NetworkX untuk komputasi graph dan python-louvain untuk community detection.
Hasil disimpan ke KolaboasiSnapshot (cached JSON).

Cara pakai:
    python utils/sinta/build_kolaboasi_graph.py
    python utils/sinta/build_kolaboasi_graph.py --sumber penelitian
    python utils/sinta/build_kolaboasi_graph.py --min-bobot 2 --max-nodes 300

Atau via Django management command / dipanggil dari ViewSet.
"""

import os, sys, time, argparse
from collections import defaultdict
from pathlib import Path

# ── Django setup ──────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ptma.settings.base')

import django
django.setup()

from django.db import connection
import networkx as nx
import community as community_louvain   # python-louvain

from apps.universities.models import SintaAuthor, KolaboasiSnapshot

# ── Palette warna komunitas ───────────────────────────────────────────────────
COMMUNITY_COLORS = [
    '#2563eb','#059669','#dc2626','#d97706','#7c3aed',
    '#0891b2','#db2777','#65a30d','#ea580c','#0d9488',
    '#4f46e5','#b45309','#be185d','#15803d','#1d4ed8',
    '#9333ea','#c2410c','#0369a1','#166534','#7e22ce',
]


def _query_pairs_sql(table: str, fk_item: str, fk_author: str) -> list[tuple[int,int]]:
    """
    Kueri SQL langsung untuk mendapatkan pasangan (author_id_a, author_id_b)
    yang muncul bersama dalam item yang sama.
    Lebih efisien dari ORM untuk self-join besar.
    """
    sql = f"""
        SELECT a.{fk_author}, b.{fk_author}
        FROM   {table} a
        JOIN   {table} b
               ON a.{fk_item} = b.{fk_item}
              AND a.{fk_author} < b.{fk_author}
    """
    with connection.cursor() as cur:
        cur.execute(sql)
        return cur.fetchall()


def build_graph(sumber: str = 'all', min_bobot: int = 1,
                max_nodes: int = 500) -> dict:
    """
    Bangun graph kolaborasi, hitung metrics, deteksi komunitas.

    Returns dict siap disimpan ke KolaboasiSnapshot.data.
    """
    t0 = time.time()
    print(f"[kolaboasi] Membangun graph sumber={sumber} min_bobot={min_bobot} …")

    # ── 1. Kumpulkan edge dari semua sumber ───────────────────────────────────
    edge_weight: defaultdict[tuple, int] = defaultdict(int)
    edge_sources: defaultdict[tuple, set] = defaultdict(set)

    sources_to_query = []
    if sumber in ('all', 'penelitian'):
        sources_to_query.append(('penelitian', 'universities_sintapenelitianauthor',
                                 'penelitian_id', 'author_id'))
    if sumber in ('all', 'pengabdian'):
        sources_to_query.append(('pengabdian', 'universities_sintapengabdianauthor',
                                 'pengabdian_id', 'author_id'))
    if sumber in ('all', 'scopus'):
        sources_to_query.append(('scopus', 'universities_sintascopusartikelauthor',
                                 'artikel_id', 'author_id'))

    for src_name, table, fk_item, fk_author in sources_to_query:
        print(f"  • Query pasangan dari {src_name} …")
        pairs = _query_pairs_sql(table, fk_item, fk_author)
        print(f"    → {len(pairs):,} pasangan ditemukan")
        for a, b in pairs:
            key = (a, b)
            edge_weight[key] += 1
            edge_sources[key].add(src_name)

    print(f"  Total edge unik (sebelum filter): {len(edge_weight):,}")

    # ── 2. Build NetworkX Graph ───────────────────────────────────────────────
    G = nx.Graph()
    for (a, b), w in edge_weight.items():
        if w >= min_bobot:
            G.add_edge(a, b, weight=w,
                       sources=list(edge_sources[(a, b)]))

    # Hapus isolated nodes (tidak ada edge)
    G.remove_nodes_from(list(nx.isolates(G)))

    print(f"  Graph: {G.number_of_nodes():,} nodes, {G.number_of_edges():,} edges")

    if G.number_of_nodes() == 0:
        return {'ready': False, 'error': 'Tidak ada data kolaborasi ditemukan.'}

    # ── 3. Metrics ────────────────────────────────────────────────────────────
    print("  Hitung degree centrality …")
    degree_dict = dict(G.degree())   # {node_id: degree}

    print("  Hitung betweenness (sampel 500 node) …")
    # Gunakan k-approximation agar cepat pada graph besar
    k_sample = min(500, G.number_of_nodes())
    betweenness = nx.betweenness_centrality(G, k=k_sample, weight='weight',
                                             normalized=True)

    # ── 4. Community Detection (Louvain) ─────────────────────────────────────
    print("  Deteksi komunitas (Louvain) …")
    partition = community_louvain.best_partition(G, weight='weight', random_state=42)
    n_komunitas = len(set(partition.values()))
    print(f"  → {n_komunitas} komunitas terdeteksi")

    # ── 5. Filter top-N nodes berdasarkan degree untuk tampilan frontend ──────
    #    Ambil max_nodes node terpenting; simpan SEMUA edge di antara mereka.
    top_nodes = sorted(degree_dict, key=lambda n: degree_dict[n], reverse=True)[:max_nodes]
    top_set   = set(top_nodes)

    # ── 6. Ambil metadata author dari DB ─────────────────────────────────────
    print("  Ambil metadata author …")
    author_qs = SintaAuthor.objects.filter(id__in=top_nodes).select_related(
        'afiliasi__perguruan_tinggi'
    ).values('id', 'nama', 'sinta_score_overall', 'sinta_id',
             'afiliasi__perguruan_tinggi__singkatan')
    author_map = {
        a['id']: {
            'pt': a['afiliasi__perguruan_tinggi__singkatan'] or '',
            'nama': a['nama'],
            'sinta_score': a['sinta_score_overall'] or 0,
            'sinta_id': a['sinta_id'] or '',
        }
        for a in author_qs
    }

    # ── 7. Layout posisi (spring layout pada subgraph top nodes) ─────────────
    print("  Hitung layout posisi …")
    subG = G.subgraph(top_set)
    pos  = nx.spring_layout(subG, weight='weight', k=2.5, iterations=80, seed=42)
    # Normalisasi ke [0.02, 0.98]
    xs = [p[0] for p in pos.values()]
    ys = [p[1] for p in pos.values()]
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    def _norm(v, lo, hi): return round((v - lo) / (hi - lo + 1e-9) * 0.96 + 0.02, 4)

    # ── 8. Komunitas stats ────────────────────────────────────────────────────
    from collections import Counter
    kom_pt: defaultdict[int, Counter] = defaultdict(Counter)
    kom_size: defaultdict[int, int]   = defaultdict(int)
    for node in top_nodes:
        k = partition.get(node, 0)
        kom_size[k] += 1
        pt = author_map.get(node, {}).get('pt', '')
        if pt:
            kom_pt[k][pt] += 1

    komunitas_list = []
    for k_id in sorted(kom_size, key=lambda x: -kom_size[x]):
        pt_dom = kom_pt[k_id].most_common(1)
        komunitas_list.append({
            'id':       k_id,
            'size':     kom_size[k_id],
            'pt_dom':   pt_dom[0][0] if pt_dom else '',
            'color':    COMMUNITY_COLORS[k_id % len(COMMUNITY_COLORS)],
        })

    # ── 9. Serialize nodes ────────────────────────────────────────────────────
    nodes_out = []
    for node_id in top_nodes:
        meta = author_map.get(node_id, {})
        p    = pos.get(node_id, (0.5, 0.5))
        k_id = partition.get(node_id, 0)
        nodes_out.append({
            'id':          node_id,
            'nama':        meta.get('nama', str(node_id)),
            'pt':          meta.get('pt', ''),
            'sinta_score': meta.get('sinta_score', 0),
            'sinta_id':    meta.get('sinta_id', ''),
            'degree':      degree_dict.get(node_id, 0),
            'betweenness': round(betweenness.get(node_id, 0), 6),
            'komunitas':   k_id,
            'color':       COMMUNITY_COLORS[k_id % len(COMMUNITY_COLORS)],
            'x':           _norm(p[0], xmin, xmax),
            'y':           _norm(p[1], ymin, ymax),
        })

    # ── 10. Serialize edges (hanya antar top nodes) ────────────────────────────
    edges_out = []
    for u, v, data in subG.edges(data=True):
        edges_out.append({
            'source':  u,
            'target':  v,
            'weight':  data.get('weight', 1),
            'sources': data.get('sources', []),
        })

    # ── 11. Top pasangan berkolaborasi ────────────────────────────────────────
    top_pairs = []
    for (a, b), w in sorted(edge_weight.items(), key=lambda x: -x[1])[:20]:
        ma = author_map.get(a, {})
        mb = author_map.get(b, {})
        top_pairs.append({
            'author1_id':   a,
            'author1_nama': ma.get('nama', ''),
            'author1_pt':   ma.get('pt', ''),
            'author2_id':   b,
            'author2_nama': mb.get('nama', ''),
            'author2_pt':   mb.get('pt', ''),
            'weight':       w,
            'sources':      list(edge_sources[(a, b)]),
        })

    # ── 12. Top node per degree & betweenness ─────────────────────────────────
    top_degree = sorted(nodes_out, key=lambda n: -n['degree'])[:15]
    top_between = sorted(nodes_out, key=lambda n: -n['betweenness'])[:15]

    # ── 13. Stats per PT ──────────────────────────────────────────────────────
    pt_collab: defaultdict[str, int] = defaultdict(int)
    for n in nodes_out:
        pt_collab[n['pt']] += n['degree']
    top_pt = sorted([{'pt': k, 'total_kolaborasi': v}
                     for k, v in pt_collab.items() if k], key=lambda x: -x['total_kolaborasi'])[:15]

    elapsed = round(time.time() - t0, 1)
    print(f"[kolaboasi] Selesai dalam {elapsed}s")

    return {
        'ready':         True,
        'sumber':        sumber,
        'min_bobot':     min_bobot,
        'elapsed_sec':   elapsed,
        'stats': {
            'total_nodes':      G.number_of_nodes(),
            'total_edges':      G.number_of_edges(),
            'total_komunitas':  n_komunitas,
            'display_nodes':    len(nodes_out),
            'display_edges':    len(edges_out),
            'density':          round(nx.density(G), 6),
            'avg_degree':       round(sum(degree_dict.values()) / max(len(degree_dict), 1), 2),
        },
        'nodes':          nodes_out,
        'edges':          edges_out,
        'komunitas_list': komunitas_list,
        'top_pairs':      top_pairs,
        'top_degree':     top_degree,
        'top_betweenness': top_between,
        'top_pt':         top_pt,
    }


# ── CLI entry point ───────────────────────────────────────────────────────────
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Build co-authorship graph PTMA')
    parser.add_argument('--sumber', default='all',
                        choices=['all', 'penelitian', 'pengabdian', 'scopus'])
    parser.add_argument('--min-bobot', type=int, default=1,
                        help='Bobot edge minimum (default: 1)')
    parser.add_argument('--max-nodes', type=int, default=500,
                        help='Maksimum node ditampilkan (default: 500)')
    parser.add_argument('--no-save', action='store_true',
                        help='Jangan simpan ke DB, hanya tampilkan statistik')
    args = parser.parse_args()

    result = build_graph(sumber=args.sumber,
                         min_bobot=args.min_bobot,
                         max_nodes=args.max_nodes)

    if result.get('ready'):
        s = result['stats']
        print(f"\n── Hasil ──────────────────────────────────")
        print(f"  Total node (full graph)  : {s['total_nodes']:,}")
        print(f"  Total edge (full graph)  : {s['total_edges']:,}")
        print(f"  Komunitas terdeteksi     : {s['total_komunitas']}")
        print(f"  Node ditampilkan         : {s['display_nodes']}")
        print(f"  Edge ditampilkan         : {s['display_edges']}")
        print(f"  Graph density            : {s['density']}")
        print(f"  Avg degree               : {s['avg_degree']}")
        print(f"\n  Top 5 pasangan terbanyak berkolaborasi:")
        for p in result['top_pairs'][:5]:
            print(f"    {p['author1_nama']} ({p['author1_pt']}) ↔ "
                  f"{p['author2_nama']} ({p['author2_pt']}) : {p['weight']}x")
        print(f"\n  Top 5 node paling terhubung (degree):")
        for n in result['top_degree'][:5]:
            print(f"    {n['nama']} ({n['pt']}) — degree={n['degree']}")

        if not args.no_save:
            snap = KolaboasiSnapshot.save_snapshot(
                result, sumber=args.sumber, min_bobot=args.min_bobot)
            print(f"\n  ✓ Disimpan ke KolaboasiSnapshot id={snap.pk}")
    else:
        print("ERROR:", result.get('error'))
