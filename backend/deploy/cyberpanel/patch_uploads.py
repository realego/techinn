"""Keep CyberPanel's security checks compatible with parsed multipart uploads."""
from pathlib import Path


def apply(cp):
    p = cp / 'CyberCP/secMiddleware.py'
    source = p.read_text()
    if '# TechInn: multipart forms may already be parsed by session middleware.' not in source:
        anchor = '    def __call__(self, request):\n'
        if anchor not in source:
            raise RuntimeError('Panel security middleware changed; review upload patch')
        source = source.replace(anchor, anchor + '''
        # TechInn: multipart forms may already be parsed by session middleware.
        # Inspect parsed fields and leave streamed file data out of body reads/logs.
        is_multipart = request.content_type == 'multipart/form-data'
        has_body = bool(request.POST or request.FILES) if is_multipart else bool(request.body)
''', 1)
        source = source.replace('if bool(request.body):', 'if has_body:')
        source = source.replace('data = json.loads(request.body)', 'data = request.POST if is_multipart else json.loads(request.body)')
        source = source.replace('logging.writeToFile(request.body)', "logging.writeToFile('Multipart form rejected by security validation.' if is_multipart else request.body)")
        p.write_text(source)
    for p in [cp / 'filemanager/static/filemanager/js/fileManager.js', cp / 'public/static/filemanager/js/fileManager.js']:
        source = p.read_text()
        if '// TechInn upload feedback' not in source:
            first = source.index('    uploader.onCompleteItem = function')
            last = source.index('    uploader.onAfterAddingFile', first)
            source = source[:first] + '''    // TechInn upload feedback
    uploader.onBeforeUploadItem = function (item) {
        item.headers['X-CSRFToken'] = getCookie('csrftoken');
    };
    uploader.onCompleteItem = function (fileItem, response, status, headers) {
        var result = response && typeof response === 'object' ? response : {};
        if (result.uploadStatus === 1) {
            $scope.errorMessage = true;
            $scope.fetchForTableSecondary(null, 'refresh');
        } else {
            $scope.errorMessage = false;
            $scope.fileName = fileItem.file.name;
            $scope.error_message = result.error_message || result.errorMessage || result.detail ||
                (status === 403 ? 'Access expired or was denied. Open File Manager again from your dashboard.' :
                 status === 413 ? 'This file exceeds the upload size limit.' :
                 status === 0 ? 'Connection interrupted. Please retry the upload.' :
                 'Upload failed (HTTP ' + status + '). Please retry.');
        }
    };

''' + source[last:]
            p.write_text(source)
    p = cp / 'filemanager/templates/filemanager/index.html'
    source = p.read_text().replace("{% static 'filemanager/js/fileManager.js' %}\"", "{% static 'filemanager/js/fileManager.js' %}?v=techinn-upload-2\"")
    p.write_text(source)


if __name__ == '__main__':
    apply(Path('/usr/local/CyberCP'))
