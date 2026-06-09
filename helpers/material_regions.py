REGION_NAMES = {
    'AN': '安宁',
    'KM': '昆明',
    'BN': '版纳',
    'DL': '大理',
    'YX': '玉溪',
    'CD': '成都',
    'GX': '广西',
}

GUANGXI_USERNAMES = {'linxiaoyin', 'wanglihua', 'leikefeng', 'tanxiang'}
GUANGXI_REAL_NAMES = {'林晓茵', '王利华', '雷克峰', '谭香'}


def is_guangxi_user(user):
    if not user:
        return False
    username = str(user.get('username') or '').strip().lower()
    real_name = str(user.get('real_name') or '').strip()
    return username in GUANGXI_USERNAMES or real_name in GUANGXI_REAL_NAMES


def resolve_material_region_code(project_code, user=None):
    code = str(project_code or '').strip().upper()
    if code.startswith('GX') or is_guangxi_user(user):
        return 'GX'
    return code[:2]


def get_region_name(code):
    prefix = str(code or '').strip().upper()[:2]
    return REGION_NAMES.get(prefix, '')


def format_project_display(project_code, project_name):
    code = str(project_code or '').strip()
    name = str(project_name or '').strip()
    city = get_region_name(code)
    parts = [part for part in (city, code, name) if part]
    return ' / '.join(parts) if parts else '-'


def generate_material_code(cursor, project_code, user=None):
    prefix = resolve_material_region_code(project_code, user) + 'LX'
    cursor.execute(
        "SELECT material_code FROM materials WHERE material_code LIKE ? ORDER BY material_code DESC LIMIT 1",
        (prefix + '%',),
    )
    last_row = cursor.fetchone()
    if last_row:
        last_code = last_row[0]
        try:
            next_num = int(last_code[len(prefix):]) + 1
        except ValueError:
            next_num = 1
    else:
        next_num = 1

    material_code = prefix + str(next_num).zfill(5)
    while True:
        cursor.execute("SELECT 1 FROM materials WHERE material_code = ?", (material_code,))
        if not cursor.fetchone():
            return material_code
        next_num += 1
        material_code = prefix + str(next_num).zfill(5)
