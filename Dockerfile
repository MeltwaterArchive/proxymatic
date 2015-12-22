FROM fedora:23

# Install HAproxy/Pen/NGinx TCP/UDP proxies, Mako for config templates
RUN dnf -y install haproxy pen nginx python-mako python-pip procps && \
	dnf clean all

ADD requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt

# Run Pen proxy as user "pen"
RUN groupadd pen && useradd -g pen pen
ENV PEN_USER pen

# Clear the default Nginx config file
RUN echo "" > /etc/nginx/conf.d/default.conf

ENV PYTHONPATH /usr/lib/python

COPY haproxy.cfg.tpl /etc/haproxy/haproxy.cfg.tpl
COPY nginx.tpl /etc/nginx/nginx.conf.tpl
COPY pen.cfg.tpl /etc/pen/pen.cfg.tpl
COPY src /usr/lib/python/proxymatic
COPY proxymatic.sh /

ENTRYPOINT ["/proxymatic.sh"]
