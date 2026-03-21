"""
Scraper SINTA — Profil Afiliasi Perguruan Tinggi

Logo SINTA (brand_sinta.png, 147x147px):
  https://sinta.kemdiktisaintek.go.id/public/assets/img/brand_sinta.png

Sumber data:
  Halaman search : /affiliations?q=[kode_pt]&search=1
  Halaman profil : /affiliations/profile/[sinta_id]

Data yang diambil:
  - Identitas   : sinta_id, sinta_kode, nama, singkatan, lokasi
  - Ringkasan   : jumlah authors, departments, journals
  - SINTA Score : overall, 3yr, productivity, productivity 3yr
  - Statistik publikasi per sumber (Scopus, GScholar, WoS, Garuda):
      documents, citations, cited_documents, citation_per_researcher
  - Distribusi kuartil Scopus: Q1, Q2, Q3, Q4, No-Q
      (data tersimpan dalam JavaScript eCharts di halaman, diekstrak via regex)
  - Last update (timestamp dari SINTA)

HTML selectors kunci:
  .stat-table            → tabel statistik publikasi (Documents/Citation/Cited/CitPerRes x 4 sumber)
  .stat-num / .stat-text → kartu ringkasan (Authors, Departments, Journals)
  .pr-num  / .pr-txt     → SINTA Score cards
  .affil-abbrev          → singkatan PT
  .affil-loc             → lokasi PT
  .affil-code            → "ID : XX  CODE : XXXXXX"
  <small>Last update ... → timestamp update terakhir di SINTA

Kolom warna di stat-table:
  text-warning  → Scopus
  text-success  → Google Scholar
  text-primary  → Web of Science  (class d-none → tersembunyi tapi datanya ada)
  text-danger   → Garuda

Kuartil Scopus disimpan dalam JavaScript eCharts:
  var quartilePie = echarts.init(...)
  data: [{value: 667, name: 'Q1'}, {value: 631, name: 'Q2'}, ...]
  → diekstrak menggunakan regex dari page source

Input  : utils/ext/namapt_list.json  (field: kode, target/keyword)
Output : utils/outs/sinta_afiliasi.json

Usage:
  # Scrape semua PT (resumable)
  python utils/sinta/scrape_sinta_afiliasi.py

  # Filter satu PT saja (testing)
  python utils/sinta/scrape_sinta_afiliasi.py --kode 061008

  # Limit jumlah PT
  python utils/sinta/scrape_sinta_afiliasi.py --limit 5

  # Tampilkan ringkasan output yang sudah ada
  python utils/sinta/scrape_sinta_afiliasi.py --status
"""

import argparse
import base64
import json
import os
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Logo SINTA (brand_sinta.png, 147×147px RGBA)
# Source: https://sinta.kemdiktisaintek.go.id/public/assets/img/brand_sinta.png
# ---------------------------------------------------------------------------
SINTA_LOGO_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAJMAAACTCAYAAACK5SsVAAAAGXRFWHRTb2Z0d2FyZQBBZG9iZSBJbWFn"
    "ZVJlYWR5ccllPAAAA2hpVFh0WE1MOmNvbS5hZG9iZS54bXAAAAAAADw/eHBhY2tldCBiZWdpbj0i77u/"
    "IiBpZD0iVzVNME1wQ2VoaUh6cmVTek5UY3prYzlkIj8+IDx4OnhtcG1ldGEgeG1sbnM6eD0iYWRvYmU6"
    "bnM6bWV0YS8iIHg6eG1wdGs9IkFkb2JlIFhNUCBDb3JlIDUuMy1jMDExIDY2LjE0NTY2MSwgMjAxMi8w"
    "Mi8wNi0xNDo1NjoyNyAgICAgICAgIj4gPHJkZjpSREYgeG1sbnM6cmRmPSJodHRwOi8vd3d3LnczLm9y"
    "Zy8xOTk5LzAyLzIyLXJkZi1zeW50YXgtbnMjIj4gPHJkZjpEZXNjcmlwdGlvbiByZGY6YWJvdXQ9IiIg"
    "eG1sbnM6eG1wTU09Imh0dHA6Ly9ucy5hZG9iZS5jb20veGFwLzEuMC9tbS8iIHhtbG5zOnN0UmVmPSJo"
    "dHRwOi8vbnMuYWRvYmUuY29tL3hhcC8xLjAvc1R5cGUvUmVzb3VyY2VSZWYjIiB4bWxuczp4bXA9Imh0"
    "dHA6Ly9ucy5hZG9iZS5jb20veGFwLzEuMC8iIHhtcE1NOk9yaWdpbmFsRG9jdW1lbnRJRD0ieG1wLmRp"
    "ZDoxNDk2NDRBMzk0MjA2ODExODIyQThEMTE3NDA5NUE4QiIgeG1wTU06RG9jdW1lbnRJRD0ieG1wLmRp"
    "ZDo0Q0M4NEQ5Q0UyRkUxMUU2OUIzMkJBNTZERkJGN0RCRCIgeG1wTU06SW5zdGFuY2VJRD0ieG1wLmlp"
    "ZDo0Q0M4NEQ5QkUyRkUxMUU2OUIzMkJBNTZERkJGN0RCRCIgeG1wOkNyZWF0b3JUb29sPSJBZG9iZSBQ"
    "aG90b3Nob3AgQ1M2IChNYWNpbnRvc2gpIj4gPHhtcE1NOkRlcml2ZWRGcm9tIHN0UmVmOmluc3RhbmNl"
    "SUQ9InhtcC5paWQ6MTU5NjQ0QTM5NDIwNjgxMTgyMkE4RDExNzQwOTVBOEIiIHN0UmVmOmRvY3VtZW50"
    "SUQ9InhtcC5kaWQ6MTQ5NjQ0QTM5NDIwNjgxMTgyMkE4RDExNzQwOTVBOEIiLz4gPC9yZGY6RGVzY3Jp"
    "cHRpb24+IDwvcmRmOlJERj4gPC94OnhtcG1ldGE+IDw/eHBhY2tldCBlbmQ9InIiPz4FRWAcAABBqUlE"
    "QVR42uxdB1xUV/Y+9N6biNIFkS5WbNhb7EajJhqTaKrpm02ym7LJ5m963UTTq4kxxoa9i5WOYAFEQHoT"
    "FVDKP3/33gEH2JjHF3/n9p8DM2/evHv3d37nnHvupWptLd2BQ9unO09Hnk7yP215WsqnBU9D+Wvxpxbf"
    "Sp4l8p/hz8s8C+QzmyeTKfIfE3hW3GkPVe0OAJMOzwCeI3n683Tj6SYHSGcNAC+Rx8Y9Gj2feQbwLL8L"
    "pp41NHgO4TmV43gZkHRuwfMCkCJ5QOAunmE8q++C6daUPpN5LpCDyLwHznOhHFS/8dx9O0itngyWahzH"
    "MJfLeZYWfxbwbIhbkLqaBqlV1Ag7rPpGOfE/2WypJTVtfbq2/hN1OYDekpPsTh3Xy8opveAKZRZepYJr"
    "xeLv6fmFVFB8na6UlNC162VUWlFBFVVVVF0je0Ya6mqkralJOlqaZGKgR+ZGhmRhaEB9LM3I3sqcLI0N"
    "qbe5KfXlfxvr63X2VwA5f53n1yZLnq1Rq1GjWnV+lnyvNWrqpMHPHeZuNf+/ulat3R9W8ucnKl9zS+x8"
    "BpKXfLcN74zrV/ODBVjOpmVRWGIKXczOo9S8QkrJzacb5R0b9dDR1iJHawtysrbkaU5D+7uQp70dOfDf"
    "tTQ0Otqq/Yrn0mvrPl1puui5uDtaMhVtXaspF9evkCxe1qGSJyLpEp06d4EOnL1ASVm5LHFudMtDNmEp"
    "5WxjRUG+7jTc3ZmGuDmJn3XgwI5YDXpguuiZqu6STN0Gpit/fAZTfx3JQh8dY0uzlIlISqXgUzF0LP4i"
    "xWfk3JKkx6WXFY3wcKUZQ3wZWI4dqRIRohlivPi5pDsGTFfWf7aUf/M/nkYd8QQTMnMoOCyWtobGCFUm"
    "+0o9w3/mZmdDMwK8aMYwf/J16tsRl0RGwyqz+5756bYGU9GvnyOGhrt6vCOe2gmWPj8dOEF7os5S0Y3S"
    "HmygqZGejjZN8Haj5RNHUpC3O6mptRsAa3k+a3Lfs+W3HZhKdqyz439t5DmsvV9sf8x5+nr3EToYe55q"
    "brekB1730R79aMWU0TSVJZaGerdcbKE85xkufC7ztgFT2W/f+PLftvPs054vdOxsIn0SfJAOnj5/e3uS1"
    "GRaOtDDmZ6ZOZEm+Q1oz9UyeM5gQMX0eDCV/bIWKSF/tocfJTCR/njzHtp4Mogl0R2WGcrqbjpLqBfn"
    "TCY/5zZzqmKeC4lQu3ViDCSkjSCVtFU3kl14jR74+Ac6EBt/F0cdPEITkmnhB99Sck6rCluwfn8xoLS7"
    "DUw8PqdWJrSlFxTSko++o1MXku+ufCeNc2mZtPD9r+lCVl5r3jZMvp5dDyaWSUgjaZUDLPvKNbr/w+8p"
    "OjntrmrrZJKUnUf3ffB1ayXUoyydlnYpmBhISGz7slVWR/F1Wv6/nyr2Usbdle6iASAt+eR7yrzcKiv5"
    "SwmUa3WlNinOTgETAwlu+d/oZssZlaP4Rik9ypZG6LmLd1e4i0d8WhYt//Rn3swlUt+Cdf2tdNN7re4S"
    "Ix1MtVSnml7jObQ1H/LSDxvowJm7zsjuGuFJyfT0N39QRZVkPxTW99+1pEZ1s0PBpFuqTWW/rkUVycus"
    "+CIfbdtL609EE9XeJUndOXZGnKE3f9/emre8XLbpXS+9mhuEKWW0pggTDq5j1IpMyS1hp2nF5z9RVfWd"
    "5ZBEyi2qTyyMDEhHS4sqq6uEp/oaq/vuds5+snIBPTh2hNSXn+I50nbGI9XZwd+pfHFr0kMebQ2QLrA1"
    "8dL3f90xQAJ4hvV3pqkDvcjF1pqcbCzIzNBAFG4iMAsgXcq7TMm5BXQwNp5Oxl9sLTHukPH6umDy7WtH"
    "/q6OUt0Fj/H9f9mRkgk9HhPkf6oc5VVVNO+DtXQ89sJtDyJrYyNaHDSEFo8ZSv1620h+X960YgoOi6G"
    "fDpwks5cyu+6G1dTJx96Wtv37STJhsEsxxEnW//NyR4HpM55PS73f1X/vpvc37rrtgTR9iC+9tmAaudv1"
    "au81UNXz3d4Q+iz4UN9V2Kir00MjB9FHjy+R+g44M5/pCDChG0mcVJV4MuEizXlnDZVXVt7yYEDp9o3y"
    "OopLaZ3vC7bNvxZOpxdmT+qwe4lOTqfnvvuzLflJbRNQGhr023MP0bQALykvR8ovgsHx7bXm3pAKJFTU"
    "vvrr5h4BJIyHJ4yg3W88Q/9ZPJNMkFetUKtmoKsjmlGAQDfc1Or0/rJ5HQokDH/nvrThn49SkI97G7LB"
    "Wj9qq6vpdV6rwuLrUl6O9X9TpYX25pstvgZo/IIkfr3/7ThEfx4N7zFqas5wf/Jx7END3Z0pkOfBqNNU"
    "UlFDDwQNoy8eW0TPzBhP0wf7iFTi+PQc0tXWpn8smEqrpo9VualiM3PoVEIyRSZdosSsXLpRVsHv1xLF"
    "ls0NAHiS/wAKv5BCGflXOh1UV67fYOOghsb59JfyctRboelYblvBtEZ+EVXWWlYOPf3NeiqtqOwxYJo1"
    "zI88+tiKv9tZmpGbrRVZmpjThw/PE+1xIJV6mZnQPQyoSn7oVvzv/3twHqk3U22LIDYqjDeEhNHF7HzS"
    "0tRkSaYmqmyiWX1tD4+lUwwUbU11lnrKbRk9BuxYHw/ac/osXZEmNdo1zqRlUZCXm2gFJEG7w8LY0Bbf"
    "TobKzhlQO/e1IhWSfMSAuU4TfScJZMKVvF1SWjZ0ODh8RuPzqhq0prOQDwBSp2tqYdmBjIBYtg6hOMU4"
    "RRwr58PHBAOEBGe/QTZD0tKFd8zNa+QX5tBhixdERrK4c/2YhWKSEAYAxpJf/+cN4UKWfUDzG0F09Jx"
    "w0SVsoqxBmCCrH5c1SsreYHWhYSJBe88vz3Rq/On0RB3R8F50PQdjkAswIrJo9lctldwpKmJ0MIhJpwp"
    "uXn0/CyZWkPhQ1FxMS+2ocgKgNU0KcCLqnlRkLpbcO2KCLOM8xvAvyunH1jaTOG/o4wbuxqfCQsLnxkW"
    "f1GUpxewGoPFh3CMGZNtNJk/ee4CObG0hg8JyXHo4gveBPBAgiDNuVZeRi74G3MsgAoSsn8fWxHC0dXS"
    "oNKyCibd2SL1RU1dg2LTMsmWpeVwdxfhBf9u33ERDkKoBhkT0RfTxAInZucKgAPYlibGdCA2nkYy2BCT"
    "RJFo1IVkmjHYl47w84HUrGGwn2umiX7Lzmp1emzaGLIzV5l2vBrHXQBMJaSi3AnxsUlvfCpEcmcNpMvu"
    "fftZpVkBUgachQfZAps3IoA5h44ItSDwC16EmZxdQFpURQOcHMiCd29f5hZfbT9AJQyyoSx9kGphx4ut"
    "juliUPixie7B6uMgqzRLI31K4O8e4OosArlY6K2sii4zwGwZRN5O9oLvwAoEqBV9W1kMcFiuUXzdSQxc"
    "AC678IqocgHHgvsA3xnSDaoP3yMhI5f2RJ5mdTWJDFhyJjF4IO1cba1oT/RZES6CMxUZsJYmhiI3vo7b"
    "7I09T/Z8TVTEoImrr5Od6P/0PtOAT7fuodYk1PVlibr/v88LkLakVBC0AICQqISzMFo8cMdQT0ekxHYm"
    "mGawpdUSkCDy6zIvsSB17gFwEqiOELZ0EOUHkDCw+2cM8eWFyBO7u6jkBkslfdqHXdzfVYDpiXvG07tb"
    "9os0YA+etIl9vZjUW5COPLaH4c7E/DTzHRB7kGkcojNnuJ84EQrey6B+e9yKQRK7ikVQqqVKZN2owc0F"
    "7ys4rEI1ke9DAej1g9sDzcR1xsQ7TMwyobfzHcpIlUUkayFf6+JGF9Nq9U0Ti+60wKlVkM1YqUXMT5Q0"
    "fjIwNKD0vv6cACeu03HzxM8EddcEOJS0MKPQ2fJxa6Ux6fu4U+vHp5W2ujetYMLUcIK5s1AcdWZbO8gYP"
    "KMe624Ze290hg7FOpvc982tHaoUOZ8AMKLgLnm8toNBQYuu/nhLdZrvX9K9RwZkqG/Elw/q89F6mJmTM0"
    "jY8ueOO60KCYIm8YWoHAul5g3tXflNZXUZV1XLOXVsjOuM1OyWMTglEMaA+vZ4QiZjDV60BLPK+f//H"
    "CvokeL9I+EdabpdbcxXlrQIbrLsqBd/TaF8P2hgSSvpamvVtndsykrJyxXEeKIdCd7mSsjJyt+sl2jq3"
    "41RS3PwTBvNXfF2HK5R41ZRXU62BIanZ2MlO7mrj6LSoJgPqawYUXPM/teZzkGH4Mqu98SyhXvttK4Um"
    "dqHHHARcRQ5WYz8T+j+hAMBK3sEfLQtnBw6iHeFx4mTLEf1dBTeULBn5+iFx8bwD1WiEh6toL4SBZL+"
    "9MedEs9ZZQ/3aZKjyfNBw8ap1ato3y8qEOQGpZ2ZF6uY27Xp8nRoiN3AfuO56QhS6i/0Jftqa96I4ccu"
    "/nqBv9x0VUqqgqGuOXVfVF7vx2TEosULzLS+FXtnohoKOuKjzw5lw9pbm4jQnHIyIqhYNddmp5pAKKBN"
    "Hxc7sHOES2n/6vDifDiCsG+cuZVBEcjr52NuJPuZtGDh8bqHhshd3kVZT73xHsaZOz7dgCbWLJRT6CG7"
    "nadea9+LBr5o+jib7e9Jn2/aLcEVVTecGilvyFWEHVyrhD1tPRtPCkYMbaUw1GtbfRTSoR1e3i9n54mgy"
    "SC20XASYsCoY10MXN3RpS84pIT/nPg2AhCrcuEvZNHOIr9QTKRuPTFBSw6UvxHT2WndJ8o7RrGUxxVt/"
    "xkGz6DQ2tLXvd+ttQ18+tkS0KURbmT1RZztRMtW2yFyVuQ4OsjQJjU+hof2dlLo/+vH995M3vAdY64pF"
    "NeR9BjDQfvHY+TJaMmZ4g/ejlTMOFmquN6aKgRDJfAZSlxwz3mXxDNNFT+MLqY/g2rZeI5B37Pp/rKRN"
    "rz5B0wb7dEj/pqZqrGXJVKVEcpXze97YsJNulKl2WMrOfZF1zlUso9p2MooGuzg2qUpB5W0bgYTnPKar"
    "gNSlYBISasictNFq+CHWibX420aaPi57vmHafsbq8QxFxYdWKBY04IZDIlS1YxTMzQhif7944Y2fWZUyi"
    "XRKc/bqW9HfAWQy+UMosd5dqk7vltyVI3mP/pL8savUZ+9jueQtl4H/Qgw0Tv87xNRtCsyTtTdtccn01"
    "K/AvyqsjmwscT6MSSSDJlkv7l4VquKN2tr1Wj6kA4JEqPr4GIGUVJ3rGu3he1N5j2GL4wDgFCT1S6HEl"
    "oB4oDn7a+touDXnqInp48VDRlkC9o6W6VlNVejVM0psqovth+mhz//WRBnqQMnfLYzbaVC/hxHdBeQuk0"
    "y1Q2z+U9W1arXvHl1wxr0kobnfFh7rgfrD74ZTHFs/cV0Onomnk4lplJMSrpoHqpqVLag5tAyuVpl26Ba"
    "2nIqmo6fS6KnZ46jZeMCxRkqnThQfraSQRRH3TxuiVIM49mPxBVt+Q5S6lGeb5Gsc127BnpMDu/vLCYG"
    "CjPRjg+9y9GeJovNdZwehe4jimrxagvFAgBaSWOSDelXKwMR3AHgbzg4Gn0t0UIR4ZBOAhP8d6+BaDOQ"
    "bundl+umrsdk0XM16jVVa678+cUGOaBWduT9oYsJ5hT5MfdwEsIRii62Sdn5oqVxflEx2ZqaCHAp63+JU"
    "wNce1mJtjjmxgbiTDoLA13RycXW0lwcp4FTwq1YZel1XnFBlVyKv8EgKqBbaKjV1t6y1SKI+L7J897u5H"
    "a30ID0gZ8OZfrxt+IN3spgqhvecnI56w4FFcC0VQ6iuFv5RnsCmOoGusIjtQUZnbp3AIhw9MMvPD+mFl"
    "r/3QVT+wYy0ZDR+QhP19sQRBdJ1tEWNYl5PenGeyKY6u+dZ5AcWFCBxj0YQEVyVfYTyY6Q6JGL0pPB1"
    "MAXwBMHryyQ/2neA+4Zpj1O0YL1ukeu1nr0uF3ApDhQmYAQDc70Gs8zgFScit5FAw4qHKp9gGRHayH0U"
    "X07PfjbEUzKpBaOIYdT1F9uHeKQIa1O/EwkiifKrS80+EAcMpwaHal1u407AUzKhrbcOnTkiSQkuMlxc"
    "AnSGC3ksy4VwUTukoCJXldoep1krRkxUduEkhTkF6fwTJVbXxV32kP9fwEGAJQ+UK1E4FmQAAAAASUVO"
    "RK5CYII="
)

# Untuk dipakai: data:image/png;base64,{SINTA_LOGO_BASE64}

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BASE_DIR     = Path(__file__).parent.parent          # utils/
INPUT_FILE   = BASE_DIR / "ext" / "namapt_list.json"
OUTPUT_FILE  = BASE_DIR / "outs" / "sinta_afiliasi.json"
OUTPUT_DIR   = Path(__file__).parent / "outs" / "affprofile"    # utils/sinta/outs/affprofile/
PUB_DIR      = Path(__file__).parent / "outs" / "publications"  # utils/sinta/outs/publications/

SINTA_BASE  = "https://sinta.kemdiktisaintek.go.id"
SEARCH_URL  = SINTA_BASE + "/affiliations?q={kode}&search=1"
PROFILE_URL = SINTA_BASE + "/affiliations/profile/{sinta_id}"

DELAY_REQUEST = 1.5   # jeda antar request (detik)
DELAY_PT      = 2.0   # jeda antar PT (detik)
TIMEOUT       = 30    # timeout request (detik)
RETRY         = 4     # jumlah retry
RETRY_WAIT    = 8     # jeda antar retry (detik)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0"
    ),
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "id,en-US;q=0.7,en;q=0.3",
    "Referer":         SINTA_BASE,
}

# Urutan kolom sumber di tabel stat-table (berdasarkan class warna di <th>)
STAT_SOURCES = [
    ("text-warning", "scopus"),
    ("text-success", "gscholar"),
    ("text-primary", "wos"),
    ("text-danger",  "garuda"),
]

# Nama baris di stat-table → field JSON
STAT_ROW_MAP = {
    "documents":              "dokumen",
    "citation":               "sitasi",
    "cited document":         "dokumen_disitasi",
    "citation per researcher":"sitasi_per_peneliti",
    "citation per researchers":"sitasi_per_peneliti",
}


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def make_session():
    s = requests.Session()
    s.headers.update(HEADERS)
    return s


def fetch(session, url, retries=RETRY):
    """GET url, kembalikan (BeautifulSoup, raw_text) atau (None, None)."""
    for attempt in range(1, retries + 1):
        try:
            r = session.get(url, timeout=TIMEOUT)
            r.raise_for_status()
            return BeautifulSoup(r.text, "lxml"), r.text
        except Exception as e:
            print(f"  [attempt {attempt}/{retries}] {url}: {e}")
            if attempt < retries:
                time.sleep(RETRY_WAIT)
    return None, None


# ---------------------------------------------------------------------------
# Step 1: Cari SINTA ID via kode PT
# ---------------------------------------------------------------------------

def find_sinta_id(session, kode):
    """
    Cari PT di SINTA menggunakan kode PT (e.g. '061008').
    Return sinta_id (string angka) atau None.
    """
    url = SEARCH_URL.format(kode=kode)
    soup, _ = fetch(session, url)
    if soup is None:
        return None

    for a in soup.find_all("a", href=True):
        m = re.search(r"/affiliations/profile/(\d+)", a["href"])
        if m:
            sinta_id = m.group(1)
            print(f"  SINTA ID: {sinta_id}")
            return sinta_id

    print(f"  SINTA ID tidak ditemukan untuk kode: {kode}")
    return None


# ---------------------------------------------------------------------------
# Step 2: Scrape halaman profil afiliasi
# ---------------------------------------------------------------------------

def _parse_number(text):
    """'1.318.091' atau '117,66' → float. Return 0.0 jika gagal."""
    if not text:
        return 0.0
    # Pisahkan format ribuan (titik) vs desimal (koma) ala Indonesia
    clean = text.strip().replace(".", "").replace(",", ".")
    try:
        return float(clean)
    except ValueError:
        return 0.0


def scrape_profil(session, sinta_id):
    """
    Ambil seluruh data profil afiliasi dari /affiliations/profile/{sinta_id}.
    Return dict.
    """
    url = PROFILE_URL.format(sinta_id=sinta_id)
    soup, raw = fetch(session, url)
    if soup is None:
        return {"sinta_profile_url": url, "error": "fetch gagal"}

    result = {"sinta_profile_url": url, "sinta_id": sinta_id}

    # --- Nama PT ---
    univ_div = soup.find("div", class_="univ-name")
    if univ_div:
        h = univ_div.find(["h3", "h2", "h1"])
        if h:
            result["nama"] = h.get_text(strip=True)

    # --- Singkatan (.affil-abbrev) ---
    el = soup.find(class_="affil-abbrev")
    if el:
        result["singkatan"] = el.get_text(strip=True)

    # --- Lokasi (.affil-loc) ---
    el = soup.find(class_="affil-loc")
    if el:
        result["lokasi"] = el.get_text(strip=True)

    # --- SINTA ID & Kode PT (.affil-code) ---
    # Format: "ID : 27  CODE : 061008"
    el = soup.find(class_="affil-code")
    if el:
        code_text = el.get_text(" ", strip=True)
        m = re.search(r"ID\s*:\s*(\d+)", code_text)
        if m:
            result["sinta_id"] = m.group(1)
        m = re.search(r"CODE\s*:\s*(\S+)", code_text)
        if m:
            result["sinta_kode"] = m.group(1)

    # --- Kartu ringkasan: Authors, Departments, Journals ---
    # <div class="stat-num">908</div>
    # <div class="stat-text">Authors</div>
    stat_nums  = soup.find_all("div", class_="stat-num")
    stat_texts = soup.find_all("div", class_="stat-text")
    for num_el, txt_el in zip(stat_nums, stat_texts):
        num = num_el.get_text(strip=True)
        lbl = txt_el.get_text(strip=True).lower()
        if num and lbl:
            field = "jumlah_" + lbl.replace(" ", "_")
            result[field] = int(_parse_number(num))

    # --- SINTA Score: pr-num / pr-txt ---
    # <div class="pr-num">1.318.091</div>
    # <div class="pr-txt">SINTA Score Overall</div>
    pr_nums = soup.find_all("div", class_="pr-num")
    pr_txts = soup.find_all("div", class_="pr-txt")
    score_map = {
        "sinta score overall":          "sinta_score_overall",
        "sinta score 3yr":              "sinta_score_3year",
        "sinta score productivity":     "sinta_score_productivity",
        "sinta score productivity 3yr": "sinta_score_productivity_3year",
    }
    for num_el, txt_el in zip(pr_nums, pr_txts):
        num = num_el.get_text(strip=True)
        lbl = txt_el.get_text(strip=True).lower()
        field = score_map.get(lbl)
        if field and num:
            result[field] = int(_parse_number(num))

    # --- Tabel statistik publikasi (table.stat-table) ---
    # Kolom: Scopus(text-warning) | GScholar(text-success) |
    #        WoS(text-primary)    | Garuda(text-danger)
    # Baris: Documents | Citation | Cited Document | Citation Per Researchers
    stat_tbl = soup.find("table", class_="stat-table")
    if stat_tbl:
        # Tentukan urutan kolom dari <thead>
        thead_ths = stat_tbl.find("thead").find_all("th") if stat_tbl.find("thead") else []
        col_source = []  # list sumber per indeks kolom (None = kolom label)
        for th in thead_ths:
            classes = th.get("class", [])
            matched = None
            for cls, src_name in STAT_SOURCES:
                if cls in classes:
                    matched = src_name
                    break
            col_source.append(matched)

        # Iterasi baris data
        for tr in stat_tbl.find("tbody").find_all("tr") if stat_tbl.find("tbody") else []:
            cells = tr.find_all("td")
            if not cells:
                continue
            row_label = cells[0].get_text(strip=True).lower()
            # Normalkan label baris
            field_suffix = None
            for key, val in STAT_ROW_MAP.items():
                if key in row_label:
                    field_suffix = val
                    break
            if not field_suffix:
                continue
            # Ambil nilai tiap kolom sumber
            for ci, cell in enumerate(cells):
                if ci >= len(col_source) or col_source[ci] is None:
                    continue
                src = col_source[ci]
                field = f"{src}_{field_suffix}"
                val = cell.get_text(strip=True)
                result[field] = _parse_number(val)

    # --- Distribusi kuartil Scopus (dari JavaScript eCharts) ---
    # Data tersimpan di JS: data:[{value:667,name:'Q1'},{value:631,name:'Q2'},...]
    if raw:
        quartile_pattern = re.compile(
            r'\{[^}]*value\s*:\s*(\d+)\s*,[^}]*name\s*:\s*[\'"]([^\'\"]+)[\'"][^}]*\}',
            re.IGNORECASE
        )
        # Cari blok JS quartile — hanya cocokkan context JS (var/let declaration atau optionQ =)
        # Hindari mencocokkan id="quartile-pie" di HTML yang ada lebih awal di dokumen
        quartile_block = ""
        m = re.search(r"var\s+quartilePie|optionQ\s*=\s*\{", raw, re.IGNORECASE)
        if m:
            quartile_block = raw[m.start():m.start() + 2000]

        for m in quartile_pattern.finditer(quartile_block):
            val, name = int(m.group(1)), m.group(2).strip()
            if name.upper() in ("Q1", "Q2", "Q3", "Q4", "NO-Q", "NOQ"):
                field = "scopus_" + name.lower().replace("-", "")
                result[field] = val

    # --- Tren publikasi Scopus per tahun (dari JavaScript eCharts) ---
    # Chart: scopus-chart-articles
    # xAxis.data: ['2011','2012',...,'2026']
    # series[0].data: [31, 27, 42, ..., 43]
    pub_history = {}
    if raw:
        m = re.search(r"getElementById\(['\"]scopus-chart-articles['\"]", raw)
        if m:
            block = raw[m.start():m.start() + 5000]
            # Ambil semua array data:[...] dalam block — index 0=tahun, 1=jumlah
            arrays = re.findall(r"data\s*:\s*\[([^\]]+)\]", block, re.DOTALL)
            if len(arrays) >= 2:
                years  = re.findall(r"['\"](\d{4})['\"]", arrays[0])
                counts = re.findall(r"\b(\d+)\b", arrays[1])
                for yr, cnt in zip(years, counts):
                    pub_history[yr] = int(cnt)
    result["pub_history"] = pub_history

    # --- Last update ---
    for small in soup.find_all("small"):
        txt = small.get_text(strip=True)
        if "last update" in txt.lower():
            m = re.search(r"last update\s*[:\-]?\s*(.+)", txt, re.IGNORECASE)
            if m:
                result["sinta_last_update"] = m.group(1).strip()
            break

    return result


# ---------------------------------------------------------------------------
# Status report
# ---------------------------------------------------------------------------

def print_status(data):
    total = len(data)
    found = sum(1 for v in data.values() if v.get("sinta_id"))
    not_found = sum(1 for v in data.values() if not v.get("sinta_id") and not v.get("error"))
    errors = sum(1 for v in data.values() if v.get("error"))
    print(f"\n{'='*50}")
    print(f"  Total PT diproses : {total}")
    print(f"  Ditemukan di SINTA: {found}")
    print(f"  Tidak ditemukan   : {not_found}")
    print(f"  Error             : {errors}")
    print(f"  Output            : {OUTPUT_FILE}")
    print(f"{'='*50}\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Scrape profil afiliasi PT dari SINTA (requests + BeautifulSoup)",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("--kode",   default="", help="Filter satu PT berdasarkan kode (e.g. 061008)")
    parser.add_argument("--limit",  type=int, default=0, help="Batasi jumlah PT (untuk testing)")
    parser.add_argument("--status", action="store_true", help="Tampilkan ringkasan output lalu keluar")
    args = parser.parse_args()

    # Load data yang sudah ada (resume)
    if OUTPUT_FILE.exists():
        with open(OUTPUT_FILE, encoding="utf-8") as f:
            results = json.load(f)
        print(f"Resume: {len(results)} PT sudah diproses")
    else:
        results = {}

    if args.status:
        print_status(results)
        return

    # Load daftar PT
    with open(INPUT_FILE, encoding="utf-8") as f:
        pt_list = json.load(f)

    # Filter jika --kode diberikan
    if args.kode:
        pt_list = [p for p in pt_list if p.get("kode") == args.kode]
        if not pt_list:
            print(f"Kode '{args.kode}' tidak ditemukan di {INPUT_FILE}")
            return

    # Limit
    if args.limit:
        pt_list = pt_list[:args.limit]

    print(f"Total PT: {len(pt_list)}")

    session = make_session()
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    PUB_DIR.mkdir(parents=True, exist_ok=True)

    for i, pt in enumerate(pt_list, 1):
        kode = pt.get("kode", "")
        nama = pt.get("target", pt.get("keyword", ""))

        if not kode:
            continue

        if kode in results:
            print(f"[{i}/{len(pt_list)}] Skip: {kode} {nama}")
            continue

        print(f"\n[{i}/{len(pt_list)}] {kode} — {nama}")

        try:
            sinta_id = find_sinta_id(session, kode)
            time.sleep(DELAY_REQUEST)

            if not sinta_id:
                results[kode] = {"sinta_id": None, "nama_input": nama, "kode_input": kode}
            else:
                data = scrape_profil(session, sinta_id)
                data["nama_input"] = nama
                data["kode_input"] = kode
                results[kode] = data

                # Ringkasan
                print(f"  Nama    : {data.get('nama', '-')}")
                print(f"  Score   : overall={data.get('sinta_score_overall', 0):,}  "
                      f"3yr={data.get('sinta_score_3year', 0):,}")
                print(f"  Authors : {data.get('jumlah_authors', 0)}")
                print(f"  Scopus  : {data.get('scopus_dokumen', 0)} dok, "
                      f"{data.get('scopus_sitasi', 0)} sitasi")
                print(f"  Q1-Q4   : {data.get('scopus_q1',0)} / {data.get('scopus_q2',0)} / "
                      f"{data.get('scopus_q3',0)} / {data.get('scopus_q4',0)} / "
                      f"NoQ={data.get('scopus_noq',0)}")
                pub = data.get("pub_history", {})
                print(f"  Pub/thn : {len(pub)} tahun — "
                      + ", ".join(f"{y}:{v}" for y, v in sorted(pub.items())[-5:])
                      + (" ..." if len(pub) > 5 else ""))

        except Exception as e:
            print(f"  ERROR: {e}")
            results[kode] = {"sinta_id": None, "error": str(e),
                             "nama_input": nama, "kode_input": kode}

        # Auto-save tiap PT — file profil individual + file gabungan
        pt_file = OUTPUT_DIR / f"{kode}_sinta_afiliasi.json"
        with open(pt_file, "w", encoding="utf-8") as f:
            json.dump(results[kode], f, ensure_ascii=False, indent=2)

        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        # Simpan tren publikasi per tahun — file terpisah
        pub_history = results[kode].get("pub_history", {})
        if pub_history:
            pub_payload = {
                "kode_pt":    kode,
                "sinta_id":   results[kode].get("sinta_id", ""),
                "nama":       results[kode].get("nama", nama),
                "pub_history": pub_history,
                "scraped_at": results[kode].get("sinta_last_update", ""),
            }
            pub_file = PUB_DIR / f"{kode}_pubhistory.json"
            with open(pub_file, "w", encoding="utf-8") as f:
                json.dump(pub_payload, f, ensure_ascii=False, indent=2)

        time.sleep(DELAY_PT)

    print(f"\n=== Selesai ===")
    print_status(results)


if __name__ == "__main__":
    main()
