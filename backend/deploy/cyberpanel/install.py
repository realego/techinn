"""Run as root to install/reapply the small TechInn panel integration."""
import os
import pwd
import secrets
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

repo = Path(__file__).resolve().parents[3]
cp = Path('/usr/local/CyberCP')
backup = Path('/root/techinn-backups') / ('panel-' + datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S'))
backup.mkdir(parents=True, mode=0o700)
paths = [
    'CyberCP/urls.py',
    'CyberCP/settings.py',
    'CyberCP/techinn_sso.py',
    'loginSystem/views.py',
    'baseTemplate/templates/baseTemplate/index.html',
    'baseTemplate/templates/baseTemplate/homePage.html',
    'baseTemplate/templates/baseTemplate/siteWorkspace.html',
    'baseTemplate/templates/baseTemplate/FileManager.html',
    'filemanager/templates/filemanager/index.html',
]
for path in paths:
    target = backup / path
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(cp / path, target)
keys = Path('/etc/techinn')
keys.mkdir(exist_ok=True, mode=0o755)
portal_key = keys / 'portal-sso.key'
key = portal_key.read_bytes() if portal_key.exists() else secrets.token_bytes(48)
for name, group in [('portal-sso.key', 'mytec3641'), ('cyberpanel-sso.key', 'cyberpanel')]:
    path = keys / name
    if path.exists() and path.read_bytes() != key:
        raise RuntimeError('Existing SSO keys differ; refusing rotation')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o640)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(key)
    os.chown(path, 0, pwd.getpwnam(group).pw_gid)
    os.chmod(path, 0o640)
shutil.copy2(Path(__file__).with_name('techinn_sso.py'), cp / 'CyberCP/techinn_sso.py')
website_template = cp / 'websiteFunctions/templates/websiteFunctions/techinnCreateWebsite.html'
if website_template.exists():
    target = backup / 'websiteFunctions/templates/websiteFunctions/techinnCreateWebsite.html'
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(website_template, target)
shutil.copy2(
    Path(__file__).with_name('techinnCreateWebsite.html'),
    website_template,
)
child_helper = Path('/usr/local/sbin/techinn-create-child')
if child_helper.exists():
    target = backup / 'usr/local/sbin/techinn-create-child'
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(child_helper, target)
shutil.copy2(Path(__file__).with_name('techinn_create_child.py'), child_helper)
os.chown(child_helper, 0, 0)
os.chmod(child_helper, 0o755)
sudoers_file = Path('/etc/sudoers.d/techinn-child-sites')
if sudoers_file.exists():
    target = backup / 'etc/sudoers.d/techinn-child-sites'
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(sudoers_file, target)
fd, sudoers_temp = tempfile.mkstemp(prefix='techinn-child-sites-', dir='/root', text=True)
try:
    with os.fdopen(fd, 'w') as stream:
        stream.write('cyberpanel ALL=(root) NOPASSWD: /usr/local/sbin/techinn-create-child ""\n')
    os.chown(sudoers_temp, 0, 0)
    os.chmod(sudoers_temp, 0o440)
    visudo = shutil.which('visudo') or '/usr/sbin/visudo'
    subprocess.run([visudo, '-cf', sudoers_temp], check=True, capture_output=True, text=True)
    os.replace(sudoers_temp, sudoers_file)
    os.chown(sudoers_file, 0, 0)
    os.chmod(sudoers_file, 0o440)
    subprocess.run([visudo, '-c'], check=True, capture_output=True, text=True)
except Exception:
    if os.path.exists(sudoers_temp):
        os.unlink(sudoers_temp)
    raise
p = cp / 'CyberCP/urls.py'
s = p.read_text()
lines = [line for line in s.splitlines() if not line.startswith('from CyberCP.techinn_sso import')]
s = '\n'.join(lines).replace(
    'from django.contrib import admin',
    'from django.contrib import admin\n'
    'from CyberCP.techinn_sso import (consume as techinn_session, '
    'create_child as techinn_create_child, create_website as techinn_create_website, '
    'install_certificate as techinn_install_certificate, '
    'submit_website_creation as techinn_submit_website_creation)',
    1,
)
if "path('api/techinn/session/'" not in s:
    s = s.replace('urlpatterns = [', "urlpatterns = [\n    path('api/techinn/session/', techinn_session),")
if "path('api/techinn/create-child/'" not in s:
    s = s.replace('urlpatterns = [', "urlpatterns = [\n    path('api/techinn/create-child/', techinn_create_child),")
if "path('api/techinn/install-certificate/'" not in s:
    s = s.replace('urlpatterns = [', "urlpatterns = [\n    path('api/techinn/install-certificate/', techinn_install_certificate),")
if "path('websites/createWebsite', techinn_create_website)" not in s:
    s = s.replace(
        "urlpatterns = [",
        "urlpatterns = [\n"
        "    path('websites/createWebsite', techinn_create_website),\n"
        "    path('websites/submitWebsiteCreation', techinn_submit_website_creation),",
        1,
    )
p.write_text(s)
p = cp / 'CyberCP/settings.py'
s = p.read_text()
if '# TechInn session integration' not in s:
    s += '''\n# TechInn session integration
SESSION_COOKIE_AGE = 21600
SESSION_SAVE_EVERY_REQUEST = True
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
MIDDLEWARE.insert(MIDDLEWARE.index('django.contrib.sessions.middleware.SessionMiddleware') + 1, 'CyberCP.techinn_sso.SiteSessionMiddleware')
'''
p.write_text(s)
p = cp / 'loginSystem/views.py'
s = p.read_text().replace('request.session.set_expiry(43200)', 'request.session.set_expiry(21600)')
p.write_text(s)
for root in [cp / 'baseTemplate/static/baseTemplate', cp / 'public/static/baseTemplate']:
    root.mkdir(parents=True, exist_ok=True)
    shutil.copy2(repo / 'public/techinn-logo-ntxuir.png', root / 'techinn-logo.png')
    shutil.copy2(repo / 'public/techinn-favicon-ntxuir.ico', root / 'techinn-favicon.ico')
p = cp / 'baseTemplate/templates/baseTemplate/index.html'
s = p.read_text().replace("{% static 'baseTemplate/cyber-panel-logo.svg' %}?v={{ CP_VERSION }}", "{% static 'baseTemplate/techinn-logo.png' %}").replace('alt="CyberPanel Logo"', 'alt="TechInn"').replace('<div class="brand">CyberPanel</div>', '<div class="brand">TechInn</div>')
s = s.replace(
    "{% static 'baseTemplate/assets/finalBase/favicon.png' %}?v={{ CP_VERSION }}",
    "{% static 'baseTemplate/techinn-favicon.ico' %}?v={{ CP_VERSION }}",
)
if 'techinn-brand-style' not in s:
    s = s.replace('</head>', '''<style id="techinn-brand-style">#header .logo-icon,.sidebar-logo .logo-icon{background:transparent!important;border:1px solid #f97316!important;border-radius:8px}#header .logo-icon img,.sidebar-logo .logo-icon img{width:34px!important;height:34px!important;object-fit:contain!important;border-radius:6px}#header .logo-text .brand,.sidebar-logo .logo-text .brand{color:#f97316!important}</style>\n</head>''')
if 'techinn-color-overrides' not in s:
    s = s.replace('</head>', '''<style id="techinn-color-overrides">
:root {
    --accent-color: #f97316;
    --accent-hover: #ea580c;
    --accent-soft-bg: rgba(249, 115, 22, 0.12);
    --accent-bg: #fff7ed;
    --accent-border: #fed7aa;
    --accent-dark: #c2410c;
    --accent-light: #ffedd5;
    --accent-primary: #f97316;
    --primary-color: #f97316;
    --primary-hover: #ea580c;
    --text-accent: #c2410c;
    --btn-primary: #c2410c;
    --btn-primary-hover: #9a3412;
    --table-head-bg: linear-gradient(135deg, #f97316 0%, #ea580c 100%);
    --focus-ring: #f97316;
}
[data-theme="dark"] {
    --accent-color: #fb923c;
    --accent-hover: #fdba74;
    --accent-soft-bg: rgba(251, 146, 60, 0.18);
    --accent-bg: #431407;
    --accent-border: #7c2d12;
    --accent-dark: #fdba74;
    --accent-light: #7c2d12;
    --accent-primary: #fb923c;
    --primary-color: #fb923c;
    --primary-hover: #fdba74;
    --text-accent: #fdba74;
    --btn-primary: #c2410c;
    --btn-primary-hover: #9a3412;
    --table-head-bg: linear-gradient(135deg, #c2410c 0%, #9a3412 100%);
    --focus-ring: #fb923c;
}
</style>
</head>''')
if 'techinn-client-panel-cleanup' not in s:
    s = s.replace('</head>', '''<style id="techinn-client-panel-cleanup">
{% if request.session.techinn_site.access_mode == 'panel' %}
.social-links,.menu-item-promo,.cp-build-card,.cp-qa-card-promo,.techinn-server-resource,.insights-section,.activity-section,.techinn-build-nudge{display:none!important}
{% endif %}
</style>
</head>''')
p.write_text(s)


def replace_template_fragment(relative_path, old, new, marker):
    template = cp / relative_path
    contents = template.read_text()
    if marker in contents:
        return
    if old not in contents:
        raise RuntimeError(f'Expected template fragment missing: {relative_path}')
    template.write_text(contents.replace(old, new, 1))


home = 'baseTemplate/templates/baseTemplate/homePage.html'
replace_template_fragment(
    home,
    '<a class="cp-qa-card" href="{% url \'buildServices\' %}">',
    '<a class="cp-qa-card cp-qa-card-promo" href="{% url \'buildServices\' %}">',
    'cp-qa-card-promo',
)
replace_template_fragment(
    home,
    '<div class="stat-card" ng-if="!statusError">\n                <div class="stat-card-header">\n                    <span class="stat-card-title">{% trans "CPU USAGE" %}</span>',
    '<div class="stat-card techinn-server-resource techinn-cpu-resource" ng-if="!statusError">\n                <div class="stat-card-header">\n                    <span class="stat-card-title">{% trans "CPU USAGE" %}</span>',
    'techinn-cpu-resource',
)
replace_template_fragment(
    home,
    '<div class="stat-card" ng-if="!statusError">\n                <div class="stat-card-header">\n                    <span class="stat-card-title">{% trans "MEMORY USAGE" %}</span>',
    '<div class="stat-card techinn-server-resource techinn-memory-resource" ng-if="!statusError">\n                <div class="stat-card-header">\n                    <span class="stat-card-title">{% trans "MEMORY USAGE" %}</span>',
    'techinn-memory-resource',
)
replace_template_fragment(
    home,
    '<div class="cp-error-state" ng-if="statusError" style="grid-column: 1 / -1;" role="alert">',
    '<div class="cp-error-state techinn-server-metrics-error" ng-if="statusError" style="grid-column: 1 / -1;" role="alert">',
    'techinn-server-metrics-error',
)
replace_template_fragment(
    'baseTemplate/templates/baseTemplate/siteWorkspace.html',
    '<div class="cp-empty-nudge" style="margin-top:18px;">',
    '<div class="cp-empty-nudge techinn-build-nudge" style="margin-top:18px;">',
    'techinn-build-nudge',
)
replace_template_fragment(
    'baseTemplate/templates/baseTemplate/FileManager.html',
    '<link rel="icon" type="image/png" href="{% static \'baseTemplate/assets/finalBase/favicon.png\' %}">',
    '<link rel="icon" type="image/x-icon" href="{% static \'baseTemplate/techinn-favicon.ico\' %}?v={{ CP_VERSION }}">',
    'baseTemplate/techinn-favicon.ico',
)
index = cp / 'baseTemplate/templates/baseTemplate/index.html'
s = index.read_text()
build_services_start = "            {l:'{% trans \"Build Services\" %}', h:'{% url \"buildServices\" %}', i:'fa-rocket', g:'{% trans \"Quick actions\" %}'},"
build_services_end = '            // Sites'
if 'techinn-client-build-services' not in s:
    start = s.find(build_services_start)
    end = s.find(build_services_end, start)
    if start < 0 or end < 0:
        raise RuntimeError('Expected command-palette build-services entries missing')
    s = s[:start] + "{% if request.session.techinn_site.access_mode != 'panel' %}\n" + s[start:end] + '{% endif %}\n' + s[end:]
    s = s.replace('var CP_PAGES = [', 'var CP_PAGES = [ // techinn-client-build-services', 1)
    index.write_text(s)
p = cp / 'filemanager/templates/filemanager/index.html'
s = p.read_text().replace('<title>{% trans "File Manager - CyberPanel" %}</title>', '<title>{% trans "File Manager - TechInn" %}</title>').replace('<i class="fa fa-folder-open"></i>', '<img src="{% static \'baseTemplate/techinn-logo.png\' %}" alt="TechInn" style="width:48px;height:48px;object-fit:contain">', 1).replace('<span class="brand">File Manager</span>', '').replace('<span class="brand" style="color:#ea580c">TechInn Files</span>', '').replace('<a href="/websites/{{ domainName }}">', '<a href="https://my.techinn.co.zw/dashboard/web/">', 1)
s = s.replace('width:30px;height:30px;object-fit:contain;border-radius:6px', 'width:48px;height:48px;object-fit:contain')
if 'techinn-files-brand' not in s:
    s = s.replace('</head>', '<style id="techinn-files-brand">#navBar .header-logo .logo-icon{width:48px;height:48px;flex:0 0 48px;background:transparent!important;border:0!important;border-radius:0;box-shadow:none!important;padding:0;transform:none!important}#navBar .header-logo .logo-icon img{width:48px!important;height:48px!important;object-fit:contain;border-radius:0}#navBar .header-logo a{gap:10px}</style>\n</head>')
p.write_text(s)
from patch_uploads import apply as patch_uploads
patch_uploads(cp)
print('Panel integration installed; originals:', backup)
