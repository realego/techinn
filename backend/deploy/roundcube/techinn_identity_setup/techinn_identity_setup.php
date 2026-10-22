<?php
/** Prompt mail users to choose their sender display name after login. */
class techinn_identity_setup extends rcube_plugin
{
    public function init()
    {
        $this->add_hook('login_after', [$this, 'after_login']);
        $rcmail = rcmail::get_instance();
        if ($rcmail->task === 'settings' && $rcmail->action === 'identities' && $rcmail->user->ID) {
            $identity = $rcmail->user->get_identity();
            if ($identity && trim((string) ($identity['name'] ?? '')) === '') {
                $rcmail->output->set_env('techinn_setup_identity', (int) $identity['identity_id']);
                $this->include_script('setup.js');
            }
        }
    }

    public function after_login($args)
    {
        $rcmail = rcmail::get_instance();
        $identity = $rcmail->user->get_identity();
        if ($identity && trim((string) ($identity['name'] ?? '')) === '') {
            $args = [
                '_task' => 'settings',
                '_action' => 'identities',
                '_iid' => $identity['identity_id'],
            ];
        }
        return $args;
    }
}
