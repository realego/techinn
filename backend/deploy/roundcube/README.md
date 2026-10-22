# TechInn Roundcube mailbox submission and identity setup

Customer webmail submits through `tls://mail.techinn.co.zw:587`, with `smtp_user = '%u'` and `smtp_pass = '%p'`. Keep TLS certificate verification enabled. These placeholders reuse the authenticated mailbox credentials; do not embed shared relay credentials. The local Postfix submission service verifies authenticated sender ownership. Website transactional emails keep their separate configured relay.

Install the `techinn_identity_setup` directory into Roundcube's plugins directory and add `techinn_identity_setup` to its enabled plugins. It opens Settings > Identities for users whose default sender name is empty, selects their existing identity and prompts them to save a name/signature. A saved name returns future logins to Mail. No password is changed and no email is sent by this plugin.

2026-10-20: removed the legacy shared external SMTP relay from live Roundcube. It rejected info@vmsecurity.co.zw with 550 5.7.1 sender domain not verified. Verified local submission TLS and sender ownership mapping without sending mail. Personalized webmail reconciliation now also publishes the existing server DKIM public key when missing, preserving existing DNS records.
