"""Read-only smoke check against the running production signature-sheet route."""
import re
import sqlite3
import sys
from pathlib import Path
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    import config
    from app import app

    print('signature_runtime_python=' + sys.version.split()[0])
    with sqlite3.connect(Path(config.DATABASE_PATH).as_uri() + '?mode=ro', uri=True) as conn:
        admin = conn.execute(
            "SELECT u.id FROM users u JOIN roles r ON r.id=u.role_id "
            "WHERE r.role_name='系统管理员' ORDER BY u.id LIMIT 1"
        ).fetchone()
        if not admin:
            raise RuntimeError('Signature smoke check requires an existing administrator')
        ids = [row[0] for row in conn.execute(
            'SELECT id FROM purchase_inquiries ORDER BY id DESC LIMIT 5'
        )]
        if not ids:
            print('signature_check=no_inquiries')
            return

    # Ephemeral signed session used only for local, read-only HTTP requests.
    serializer = app.session_interface.get_signing_serializer(app)
    cookie = serializer.dumps({'user': {'id': admin[0]}})
    for inquiry_id in ids:
        request = Request(
            'http://127.0.0.1:5000/api/purchase-inquiries/{}/approval-print'.format(inquiry_id),
            headers={'Cookie': '{}={}'.format(app.config['SESSION_COOKIE_NAME'], cookie)},
        )
        with urlopen(request, timeout=20) as response:
            html = response.read().decode('utf-8')
            if response.status != 200 or '<table' not in html or '历史最低价' not in html:
                raise RuntimeError('Signature rendering failed for inquiry {}'.format(inquiry_id))
        prices = re.findall(r'<td class="num historical-price">([^<]*)</td>', html)
        if any(price != '—' and '/' not in price for price in prices):
            raise RuntimeError('Historical tax rate missing for inquiry {}'.format(inquiry_id))
        print('signature_check inquiry_id={} http=200 historical_cells={} prices={}'.format(
            inquiry_id, len(prices), ','.join(prices).encode('ascii', 'backslashreplace').decode('ascii')
        ))


if __name__ == '__main__':
    main()
