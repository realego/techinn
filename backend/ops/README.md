# TechInn service hardening

`techinn-dovecot-config-guard` is installed at `/usr/local/sbin/techinn-dovecot-config-guard` on the VPS and runs as a `dovecot.service` `ExecStartPre` guard. CyberPanel can append SNI blocks before a certificate exists; the guard removes only blocks whose certificate or key is missing, validates the resulting configuration, and lets Dovecot start. Once a certificate is issued, CyberPanel can add the SNI block again.
