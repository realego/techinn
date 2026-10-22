if (window.rcmail) {
  rcmail.addEventListener('init', function () {
    if (rcmail.env.techinn_setup_identity && rcmail.identity_list) {
      rcmail.identity_list.select(String(rcmail.env.techinn_setup_identity));
      rcmail.display_message('Set your sender name and optional signature, then save. Use Mail to return to your inbox.', 'notice');
    }
  });
}
