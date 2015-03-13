FROM centos:6

# Install Epel YUM repo
RUN rpm -i "https://dl.fedoraproject.org/pub/epel/6/x86_64/epel-release-6-8.noarch.rpm"

# Install HAproxy/Pen TCP/UDP proxies, Mako for config templates
RUN yum -y install haproxy pen python-mako && yum clean all

# Run Pen proxy as user "pen"
RUN groupadd pen && useradd -g pen pen
ENV PEN_USER pen

ENV PYTHONPATH /usr/lib/python

COPY haproxy.cfg.tpl /etc/haproxy/haproxy.cfg.tpl
COPY pen.cfg.tpl /etc/pen/pen.cfg.tpl
COPY src/main/python/proxymatic /usr/lib/python/proxymatic
COPY proxymatic.sh /

ENTRYPOINT ["/proxymatic.sh"]
