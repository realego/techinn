"""Run as root to install/reapply the small TechInn panel integration."""
import os
import pwd
import secrets
import shutil
from datetime import datetime, timezone
from pathlib import Path

repo = Path(__file__).resolve().parents[3]
cp = Path('/usr/local/CyberCP')
backup = Path('/root/techinn-backups') / ('panel-' + datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S'))
backup.mkdir(parents=True, mode=0o700)
paths = ['CyberCP/urls.py', 'CyberCP/settings.py', 'loginSystem/views.py', 'baseTemplate/templates/baseTemplate/index.html', 'filemanager/templates/filemanager/index.html']
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
p = cp / 'CyberCP/urls.py'
s = p.read_text()
if 'techinn/session/' not in s:
    s = s.replace('from django.contrib import admin', 'from django.contrib import admin\nfrom CyberCP.techinn_sso import consume as techinn_session')
    s = s.replace('urlpatterns = [', "urlpatterns = [\n    path('api/techinn/session/', techinn_session),")
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
p = cp / 'baseTemplate/templates/baseTemplate/index.html'
s = p.read_text().replace("{% static 'baseTemplate/cyber-panel-logo.svg' %}?v={{ CP_VERSION }}", "{% static 'baseTemplate/techinn-logo.png' %}").replace('alt="CyberPanel Logo"', 'alt="TechInn"').replace('<div class="brand">CyberPanel</div>', '<div class="brand">TechInn</div>')
if 'techinn-brand-style' not in s:
    s = s.replace('</head>', '''<style id="techinn-brand-style">#header .logo-icon,.sidebar-logo .logo-icon{background:transparent!important;border:1px solid #f97316!important;border-radius:8px}#header .logo-icon img,.sidebar-logo .logo-icon img{width:34px!important;height:34px!important;object-fit:contain!important;border-radius:6px}#header .logo-text .brand,.sidebar-logo .logo-text .brand{color:#f97316!important}</style>\n</head>''')
p.write_text(s)
p = cp / 'filemanager/templates/filemanager/index.html'
s = p.read_text().replace('<title>{% trans "File Manager - CyberPanel" %}</title>', '<title>{% trans "File Manager - TechInn" %}</title>').replace('<i class="fa fa-folder-open"></i>', '<img src="{% static \'baseTemplate/techinn-logo.png\' %}" alt="TechInn" style="width:48px;height:48px;object-fit:contain">', 1).replace('<span class="brand">File Manager</span>', '').replace('<span class="brand" style="color:#ea580c">TechInn Files</span>', '').replace('<a href="/websites/{{ domainName }}">', '<a href="https://my.techinn.co.zw/dashboard/web/">', 1)
s = s.replace('width:30px;height:30px;object-fit:contain;border-radius:6px', 'width:48px;height:48px;object-fit:contain')
if 'techinn-files-brand' not in s:
    s = s.replace('</head>', '<style id="techinn-files-brand">#navBar .header-logo .logo-icon{width:48px;height:48px;flex:0 0 48px;background:transparent!important;border:0!important;border-radius:0;box-shadow:none!important;padding:0;transform:none!important}#navBar .header-logo .logo-icon img{width:48px!important;height:48px!important;object-fit:contain;border-radius:0}#navBar .header-logo a{gap:10px}</style>\n</head>')
p.write_text(s)
from patch_uploads import apply as patch_uploads
patch_uploads(cp)
print('Panel integration installed; originals:', backup)
