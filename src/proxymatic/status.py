import logging
from BaseHTTPServer import BaseHTTPRequestHandler
from proxymatic import util

class StatusEndpoint(object):
    def __init__(self, source):
        self._source = source
        self._terminate = False

    def start(self):
        status = self

        class RequestHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == '/status':
                    if status._terminate:
                        code, message = 503, "TERMINATING\n"
                    elif status._source.isHealthy():
                        code, message = 200, "OK\n"
                    else:
                        code, message = 503, "INITIALIZING\n"

                    self.send_response(code)
                    self.end_headers()
                    self.wfile.write(message)
                else:
                    self.send_error(404)

            def log_request(self, *args, **kwargs):
                # Ignore request logging for status checks
                pass

        server = util.UnixHTTPServer('/tmp/proxymatic-status.sock', RequestHandler)
        util.run(server.serve_forever, "Error serving HTTP status endpoint")
        logging.debug("Enabled /status endpoint on /tmp/proxymatic-status.sock")

    def terminate(self):
        self._terminate = True

    def isTerminating(self):
        return self._terminate
