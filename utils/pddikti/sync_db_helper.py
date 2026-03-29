"""Helper untuk update status SinkronisasiJadwal dari sync scripts."""

from datetime import datetime


def ensure_connection(conn):
    """Ping dan reconnect jika koneksi MySQL sudah putus (gone away)."""
    try:
        conn.ping(reconnect=True)
    except Exception:
        pass


def update_jadwal_status(conn, jadwal_id, status, pesan='', pid=-1):
    """
    Update status sinkronisasi jadwal di DB.

    Args:
        conn      : koneksi pymysql aktif
        jadwal_id : int — id SinkronisasiJadwal, atau None (no-op)
        status    : 'menunggu' | 'berjalan' | 'selesai' | 'error'
        pesan     : string pesan / log ringkasan
        pid       : int (proses PID), None untuk clear, -1 untuk tidak diubah
    """
    if jadwal_id is None:
        return
    ensure_connection(conn)
    now = datetime.now()
    with conn.cursor() as cur:
        if pid == -1:
            # Jangan ubah kolom pid
            cur.execute(
                "UPDATE universities_sinkronisasijadwal "
                "SET status_terakhir=%s, pesan_terakhir=%s, last_run=%s "
                "WHERE id=%s",
                (status, pesan, now, jadwal_id),
            )
        elif pid is None:
            cur.execute(
                "UPDATE universities_sinkronisasijadwal "
                "SET status_terakhir=%s, pesan_terakhir=%s, pid=NULL, last_run=%s "
                "WHERE id=%s",
                (status, pesan, now, jadwal_id),
            )
        else:
            cur.execute(
                "UPDATE universities_sinkronisasijadwal "
                "SET status_terakhir=%s, pesan_terakhir=%s, pid=%s, last_run=%s "
                "WHERE id=%s",
                (status, pesan, pid, now, jadwal_id),
            )
    conn.commit()
