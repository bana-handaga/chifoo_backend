"""
Estimasi WCU Subject Area jurnal menggunakan pendekatan Hybrid:
  1. Rule-based keyword matching (presisi tinggi)
  2. TF-IDF + Logistic Regression untuk sisa yang tidak tercover rule

5 WCU Groups (sesuai standar QS World University Rankings):
  - Natural Sciences
  - Engineering & Technology
  - Life Sciences & Medicine
  - Social Sciences & Management
  - Arts & Humanities

Penggunaan:
  python manage.py predict_wcu_area             # dry-run
  python manage.py predict_wcu_area --save      # simpan ke wcu_area
  python manage.py predict_wcu_area --save --min-confidence 0.45
"""
import re
from django.core.management.base import BaseCommand
from apps.universities.models import SintaJurnal

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.multiclass import OneVsRestClassifier
from sklearn.preprocessing import MultiLabelBinarizer
from sklearn.pipeline import Pipeline
from sklearn.model_selection import cross_validate
import warnings
warnings.filterwarnings('ignore')

# ─────────────────────────────────────────────────────────────────────────────
# 5 WCU Groups
# ─────────────────────────────────────────────────────────────────────────────
WCU_GROUPS = [
    'Natural Sciences',
    'Engineering & Technology',
    'Life Sciences & Medicine',
    'Social Sciences & Management',
    'Arts & Humanities',
]

# ─────────────────────────────────────────────────────────────────────────────
# Mapping SINTA category → WCU (untuk jurnal yang sudah berlabel)
# ─────────────────────────────────────────────────────────────────────────────
SINTA_TO_WCU = {
    'Science':     'Natural Sciences',
    'Engineering': 'Engineering & Technology',
    'Agriculture': 'Engineering & Technology',
    'Health':      'Life Sciences & Medicine',
    'Social':      'Social Sciences & Management',
    'Economy':     'Social Sciences & Management',
    'Education':   'Social Sciences & Management',
    'Humanities':  'Arts & Humanities',
    'Art':         'Arts & Humanities',
    'Religion':    'Arts & Humanities',
}

# ─────────────────────────────────────────────────────────────────────────────
# Rule-based keyword dictionary
# Kata kunci diurutkan dari yang paling spesifik ke umum.
# Format: { 'wcu_group': [keyword, ...] }
# ─────────────────────────────────────────────────────────────────────────────
RULES = {
    'Life Sciences & Medicine': [
        # Farmasi & Obat
        r'farmasi', r'pharmacy', r'pharmaceutical', r'apoteker', r'obat',
        # Kedokteran
        r'kedokteran', r'medical', r'medicine', r'klinik', r'clinical',
        r'dokter', r'physician',
        # Keperawatan & Kebidanan
        r'keperawatan', r'nursing', r'kebidanan', r'midwi',
        # Kesehatan umum
        r'kesehatan', r'health', r'gizi', r'nutrisi', r'nutrition',
        r'epidemiologi', r'epidemiol',
        # Biologi & Hayati
        r'biologi', r'biology', r'biomedik', r'biomedic',
        r'anatomi', r'fisiologi', r'patologi', r'mikrobiologi',
        r'biokimia', r'biochem',
        # Pertanian & Peternakan
        r'pertanian', r'agri(?!ndustri)', r'agronomie?', r'peternakan',
        r'veteriner', r'veterinary', r'perikanan', r'kelautan', r'kehutanan',
        r'perkebunan', r'budidaya', r'tanaman', r'pangan',
        r'hortikult', r'forestry', r'aqua',
    ],
    'Engineering & Technology': [
        # Teknik spesifik
        r'teknik(?! tulisan)', r'engineering', r'rekayasa',
        r'elektro(?!nomi)', r'electrical', r'electronic',
        r'mesin', r'mechanical', r'otomotif', r'automotive',
        r'sipil(?! hukum)', r'civil(?! law)', r'konstruksi', r'struktur bangunan',
        r'informatika', r'informatics', r'komputer', r'computer',
        r'sistem informasi', r'information system',
        r'teknologi informasi', r'information technolog',
        r'pemrograman', r'programming', r'software', r'perangkat lunak',
        r'jaringan komputer', r'network',
        r'kecerdasan buatan', r'artificial intelligen', r'\bai\b', r'machine learning',
        r'data science', r'data mining',
        r'kimia(?! sosial)', r'chemistry(?! social)', r'chemical',
        r'fisika(?! sosial)', r'physics(?! social)',
        r'material', r'metalurgi', r'metallurgy',
        r'industri', r'industrial', r'manufaktur', r'manufacturing',
        r'lingkungan hidup', r'environmental',
        r'energi', r'energy', r'geologi', r'geology',
        r'geodesi', r'geomatika', r'geomatics',
        r'arsitektur', r'architecture',
        r'planologi', r'urban planning',
        r'tambang', r'mining', r'perminyakan', r'petroleum',
    ],
    'Natural Sciences': [
        r'matematika', r'mathematics', r'\bmath\b',
        r'statistik', r'statistic',
        r'astronomi', r'astronomy', r'astrofisika',
        r'fisika murni', r'pure physics',
        r'kimia murni', r'pure chemistry',
        r'biologi murni', r'pure biology',
        r'ilmu alam', r'natural science',
    ],
    'Arts & Humanities': [
        r'agama', r'religion', r'keagamaan',
        r'islam(?!ic econom)', r'islamic(?! econom)', r'quran', r"qur'?an",
        r'fiqh', r'aqidah', r'syariah(?! ekonomi)', r'sharia(?! econom)',
        r'pesantren', r'madrasah', r'tahfidz',
        r'filsafat', r'philosophy',
        r'seni(?! bela)', r'\barts?\b', r'budaya', r'culture', r'kultural',
        r'sastra', r'literature', r'linguistik', r'linguistic',
        r'bahasa(?! dan pendidikan)', r'language(?! education)',
        r'humaniora', r'humanities',
        r'sejarah', r'history', r'arkeologi', r'archaeology',
        r'komunikasi(?! bisnis)', r'communication(?! business)',
        r'jurnalistik', r'journalism',
        r'perpustakaan', r'library',
        r'musik', r'music', r'teater', r'theatre', r'drama',
        r'desain', r'design',
    ],
    'Social Sciences & Management': [
        r'pendidikan', r'education', r'pembelajaran', r'learning',
        r'pengajaran', r'teaching', r'kurikulum', r'curriculum',
        r'sekolah', r'school', r'siswa', r'mahasiswa',
        r'guru', r'teacher', r'dosen', r'lecturer',
        r'ekonomi', r'economics?', r'economy',
        r'manajemen', r'management',
        r'akuntansi', r'accounting',
        r'keuangan', r'finance', r'financial',
        r'bisnis', r'business',
        r'perbankan', r'banking',
        r'pemasaran', r'marketing',
        r'administrasi', r'administration',
        r'sosial', r'social',
        r'sosiologi', r'sociology',
        r'psikologi', r'psychology',
        r'hukum', r'law', r'legal',
        r'politik', r'political', r'pemerintahan', r'governance',
        r'kebijakan', r'policy',
        r'hubungan internasional', r'international relation',
        r'kewarganegaraan', r'civics',
        r'geografi(?! teknik)', r'geography(?! engineer)',
        r'pariwisata', r'tourism',
    ],
}

# Compile regex (case-insensitive)
COMPILED_RULES: dict[str, list] = {
    group: [re.compile(kw, re.IGNORECASE) for kw in kws]
    for group, kws in RULES.items()
}

# Urutan prioritas saat ada konflik kelas
WCU_PRIORITY = {
    'Life Sciences & Medicine':    1,
    'Engineering & Technology':    2,
    'Natural Sciences':            3,
    'Arts & Humanities':           4,
    'Social Sciences & Management': 5,
}


def rule_predict(text: str) -> tuple[list[str], bool]:
    """
    Terapkan rule-based keyword matching.
    Returns: (list_of_wcu_groups, is_high_confidence)
    """
    found: set[str] = set()
    for group, patterns in COMPILED_RULES.items():
        for pat in patterns:
            if pat.search(text):
                found.add(group)
                break  # cukup satu keyword per group

    if not found:
        return [], False

    # Jika Natural Sciences dan Engineering keduanya muncul,
    # cek apakah ada "teknik/engineering" eksplisit untuk disambiguasi
    if 'Natural Sciences' in found and 'Engineering & Technology' in found:
        eng_explicit = any(
            p.search(text) for p in [
                re.compile(r'teknik|engineering|rekayasa|informatika|komputer', re.I)
            ]
        )
        if eng_explicit:
            found.discard('Natural Sciences')

    return sorted(found, key=lambda g: WCU_PRIORITY[g]), True


def parse_wcu_labels(subject_area: str) -> list[str]:
    """Ubah string subject_area SINTA → list WCU group."""
    if not subject_area:
        return []
    groups = set()
    for cat in subject_area.split(','):
        cat = cat.strip()
        wcu = SINTA_TO_WCU.get(cat)
        if wcu:
            groups.add(wcu)
    return sorted(groups, key=lambda g: WCU_PRIORITY[g])


def build_text(j) -> str:
    parts = [j.nama or '']
    if j.afiliasi_teks:
        parts.append(j.afiliasi_teks)
    return ' '.join(parts)


class Command(BaseCommand):
    help = 'Estimasi WCU subject area jurnal (Hybrid: Rule + ML)'

    def add_arguments(self, parser):
        parser.add_argument('--save', action='store_true',
                            help='Simpan prediksi ke field wcu_area')
        parser.add_argument('--min-confidence', type=float, default=0.45,
                            help='Threshold ML (default 0.45)')

    def handle(self, *args, **options):
        save       = options['save']
        min_conf   = options['min_confidence']

        self.stdout.write('\n' + '═' * 65)
        self.stdout.write('  Hybrid WCU Area Estimator  (Rule-based + TF-IDF + LogReg)')
        self.stdout.write('═' * 65)

        # ── Ambil semua jurnal (exclude logo_base64 agar tidak OOM/timeout) ──
        FIELDS = ['id', 'nama', 'afiliasi_teks', 'subject_area', 'wcu_area']
        all_journals = list(SintaJurnal.objects.only(*FIELDS))
        unlabeled    = [j for j in all_journals
                        if not (j.subject_area or '').strip()]
        labeled      = [j for j in all_journals
                        if (j.subject_area or '').strip()]

        self.stdout.write(f'\nTotal jurnal     : {len(all_journals)}')
        self.stdout.write(f'Berlabel (SINTA) : {len(labeled)}')
        self.stdout.write(f'Unlabeled        : {len(unlabeled)}')

        # ── TAHAP 1: Rule-based pada unlabeled ─────────────────────────
        self.stdout.write('\n[TAHAP 1] Rule-based keyword matching...')
        rule_results:  list[tuple] = []  # (jurnal, labels, 'rule')
        ml_candidates: list       = []  # jurnal yang tidak tercover rule

        for j in unlabeled:
            text = build_text(j)
            labels, confident = rule_predict(text)
            if labels:
                rule_results.append((j, labels, 'rule'))
            else:
                ml_candidates.append(j)

        self.stdout.write(f'  Tercover rule : {len(rule_results)} jurnal')
        self.stdout.write(f'  Ke ML         : {len(ml_candidates)} jurnal')

        # ── TAHAP 2: ML pada sisa ───────────────────────────────────────
        ml_results: list[tuple] = []

        if ml_candidates:
            self.stdout.write('\n[TAHAP 2] TF-IDF + OneVsRest(LogReg)...')

            # Siapkan training data dari (labeled SINTA) + (rule_results sebagai pseudo-label)
            X_train_raw: list[str] = []
            y_train_raw: list[list[str]] = []

            for j in labeled:
                labels = parse_wcu_labels(j.subject_area)
                if labels:
                    X_train_raw.append(build_text(j))
                    y_train_raw.append(labels)

            # Tambahkan rule_results sebagai data augmentation
            for j, labels, _ in rule_results:
                X_train_raw.append(build_text(j))
                y_train_raw.append(labels)

            mlb     = MultiLabelBinarizer(classes=WCU_GROUPS)
            Y_train = mlb.fit_transform(y_train_raw)

            pipeline = Pipeline([
                ('tfidf', TfidfVectorizer(
                    analyzer='char_wb',
                    ngram_range=(3, 5),
                    min_df=2, max_features=12000, sublinear_tf=True,
                )),
                ('clf', OneVsRestClassifier(
                    LogisticRegression(
                        C=2.0, max_iter=500, solver='lbfgs',
                        class_weight='balanced',
                    )
                )),
            ])

            # Cross-validation (hanya pada labeled asli — lebih jujur)
            mlb2   = MultiLabelBinarizer(classes=WCU_GROUPS)
            y_orig = [parse_wcu_labels(j.subject_area) for j in labeled]
            Y_orig = mlb2.fit_transform([y for y in y_orig if y])
            X_orig = [build_text(j) for j, y in zip(labeled, y_orig) if y]
            cv = cross_validate(
                Pipeline([
                    ('tfidf', TfidfVectorizer(analyzer='char_wb', ngram_range=(3, 5),
                                              min_df=2, max_features=12000, sublinear_tf=True)),
                    ('clf', OneVsRestClassifier(
                        LogisticRegression(C=2.0, max_iter=500, class_weight='balanced'))),
                ]),
                X_orig, Y_orig, cv=5,
                scoring=['f1_samples', 'accuracy'], n_jobs=-1,
            )
            f1  = cv['test_f1_samples'].mean()
            acc = cv['test_accuracy'].mean()
            self.stdout.write(f'  CV F1-Score  : {f1:.3f} ({f1*100:.1f}%)')
            self.stdout.write(f'  CV Accuracy  : {acc:.3f} ({acc*100:.1f}%)')

            # Latih pada semua data (labeled + pseudo)
            pipeline.fit(X_train_raw, Y_train)

            # Prediksi
            X_ml   = [build_text(j) for j in ml_candidates]
            tfidf  = pipeline.named_steps['tfidf']
            clf    = pipeline.named_steps['clf']
            X_vec  = tfidf.transform(X_ml)
            probas = np.column_stack([
                est.predict_proba(X_vec)[:, 1]
                for est in clf.estimators_
            ])

            for i, j in enumerate(ml_candidates):
                probs  = probas[i]
                labels = [WCU_GROUPS[k] for k, p in enumerate(probs) if p >= min_conf]
                if not labels:
                    best   = int(np.argmax(probs))
                    labels = [WCU_GROUPS[best]]
                conf   = float(probs.max())
                ml_results.append((j, labels, f'ml:{conf:.2f}'))

        # ── TAHAP 3 (opsional): Jurnal berlabel → isi wcu_area dari mapping ──
        labeled_wcu: list[tuple] = []
        for j in labeled:
            lbl = parse_wcu_labels(j.subject_area)
            if lbl:
                labeled_wcu.append((j, lbl, 'mapped'))

        # ── Gabungkan semua ──────────────────────────────────────────────
        all_results = rule_results + ml_results

        # ── Statistik ───────────────────────────────────────────────────
        self.stdout.write('\n📊 Distribusi prediksi unlabeled:')
        grp_count = {g: 0 for g in WCU_GROUPS}
        sources   = {'rule': 0, 'ml': 0}
        for _, labels, src in all_results:
            for lbl in labels:
                grp_count[lbl] += 1
            if src == 'rule':
                sources['rule'] += 1
            else:
                sources['ml'] += 1

        for grp, cnt in grp_count.items():
            bar = '█' * (cnt // 8)
            self.stdout.write(f'  {grp:<35} {cnt:4d}  {bar}')
        self.stdout.write(f'\n  Sumber: Rule={sources["rule"]}, ML={sources["ml"]}')

        # Preview per WCU group
        self.stdout.write('\n📋 Contoh prediksi per WCU group:')
        shown: dict[str, int] = {g: 0 for g in WCU_GROUPS}
        for j, labels, src in all_results:
            for lbl in labels:
                if shown[lbl] < 4:
                    self.stdout.write(
                        f'  [{src:>10}] {lbl:<35} {j.nama[:50]}')
                    shown[lbl] += 1

        # ── Simpan jika --save ───────────────────────────────────────────
        if save:
            self.stdout.write('\n💾 Menyimpan prediksi unlabeled → wcu_area...')
            bulk_unlabeled = []
            for j, labels, _ in all_results:
                j.wcu_area = ', '.join(labels)
                bulk_unlabeled.append(j)
            SintaJurnal.objects.bulk_update(bulk_unlabeled, ['wcu_area'])
            self.stdout.write(f'  Unlabeled tersimpan: {len(bulk_unlabeled)}')

            self.stdout.write('💾 Mengisi wcu_area untuk jurnal berlabel (dari mapping SINTA)...')
            bulk_labeled = []
            for j, labels, _ in labeled_wcu:
                j.wcu_area = ', '.join(labels)
                bulk_labeled.append(j)
            SintaJurnal.objects.bulk_update(bulk_labeled, ['wcu_area'])
            self.stdout.write(
                self.style.SUCCESS(
                    f'  Berlabel tersimpan: {len(bulk_labeled)}\n'
                    f'✔ Total wcu_area terisi: {len(bulk_unlabeled) + len(bulk_labeled)} jurnal'
                ))
        else:
            self.stdout.write(
                '\n  ℹ️  Dry-run — jalankan dengan --save untuk menyimpan.')

        self.stdout.write('═' * 65 + '\n')
