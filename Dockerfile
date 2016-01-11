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

# Add tini to avoid PID 1 zombie reaping problem
RUN curl -o /usr/local/bin/tini -fsSL https://github.com/krallin/tini/releases/download/v0.8.4/tini && \
    chmod +x /usr/local/bin/tini && \
    echo "c4894d809f3e2bdcc9c2e20db037d80b17944fc6 /usr/local/bin/tini" | sha1sum -c -

ENV PYTHONPATH /usr/lib/python

COPY haproxy.cfg.tpl /etc/haproxy/haproxy.cfg.tpl
COPY nginx.tpl /etc/nginx/nginx.conf.tpl
COPY pen.cfg.tpl /etc/pen/pen.cfg.tpl
COPY src /usr/lib/python/proxymatic

ENTRYPOINT ["tini", "--", "python", "/usr/lib/python/proxymatic/main.py"]
