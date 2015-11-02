import logging, os, re, signal, time, threading, traceback, urllib2, httplib, socket

def post(url, data='{}'):
    request = urllib2.Request(url, data)
    request.add_header('Content-Type', 'application/json; charset=utf-8')
    request.get_method = lambda: 'POST'
    return urllib2.urlopen(request)

def delete(url):
    request = urllib2.Request(url)
    request.get_method = lambda: 'DELETE'
    return urllib2.urlopen(request)

def rget(root, *args):
    node = root
    for arg in args:
        node = node.get(arg, {})
    return node
    
def mangle(key):
    return re.sub('[^a-zA-Z0-9]+', '_', re.sub('^[^a-zA-Z0-9]+', '', key))

def alive(pidfile):
    """
    Checks if a process identified is still running.
    @param  pidfile File containing the PID of the process to check for
    """
    try:
        with open(pidfile) as f:
            pid = f.read()
            os.kill(int(pid), 0)
    except (IOError, OSError):
        return False
    return True

def kill(pidfile, sig=signal.SIGKILL):
    """
    Signal a process
    @param  pidfile File containing PID of process to signal
    @param  sig     Signal to send, defalts to signal.SIGKILL
    """
    pid = None
    name = os.path.basename(pidfile)
    try:
        with open(pidfile) as f:
            pid = f.read()
            os.kill(int(pid), sig)

        logging.debug("Sent signal '%s' to '%s'", sig, name)
        return True
    except IOError:
        logging.debug("PID file '%s' doesn't exist", pidfile)
    except Exception, e:
        logging.warn("Failed to send signal '%s' to '%s' with PID %s: %s", sig, name, pid, str(e))
        logging.debug(traceback.format_exc())
    return False

def run(action, errormsg="Connection error: %s"):
    """
    Run action() in background forever and retry with exponential backoff in case of errors.
    """
    def routine():
        timeout = 1
        while True:
            try:
                action()
                timeout = 1
            except Exception, e:
                logging.warn(errormsg, str(e))
                logging.debug(traceback.format_exc())
                time.sleep(timeout)
                timeout = min(timeout * 2, 30)
    
    thread = threading.Thread(target=routine)
    thread.daemon = True
    thread.start()

def shell(cmd):
    return subprocess.call(cmd, shell=True)

class UnixHTTPConnection(httplib.HTTPConnection):
    """
    Subclass of Python library HTTPConnection that uses a unix-domain socket.
    """
    def __init__(self, path):
        httplib.HTTPConnection.__init__(self, 'localhost')
        self.path = path
 
    def connect(self):
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(self.path)
        self.sock = sock

def unixrequest(method, socketpath, url, body=None, headers={}):
    conn = UnixHTTPConnection(socketpath)
    conn.request(method, url, body, headers)
    resp = conn.getresponse()
    return resp.read()
