# For more information on configuration, see:
# - NGinx Documentation: http://nginx.org/en/docs/
# - WebSockets with AWS ELB: https://www.built.io/blog/2014/11/websockets-on-aws-elb/
# - https://github.com/jwilder/nginx-proxy 
# - https://github.com/deis/deis/blob/master/router/rootfs/etc/confd/templates/nginx.conf

user nginx;
pid /run/nginx.pid;
error_log /proc/self/fd/2;

# Number of worker processes
worker_processes 4;

events {
    worker_connections ${int(maxconnections / 4)};
}

http {
    sendfile            on;
    tcp_nopush          on;
    tcp_nodelay         on;

    # Disable limit on Content-Length and make it up to front-end loadbalancers and services to limit it
    client_max_body_size 0;

    # The Timeout value must be greater than the front facing load balancers timeout value.
    # Default is the deis recommended timeout value for ELB - 1200 seconds + 100s extra.
    keepalive_timeout   1300s;

    # Controls how many vhosts that can be supported
    server_names_hash_max_size 512;

    # Bucket size determines max length of a vhost server name
    server_names_hash_bucket_size 256;

    types_hash_max_size 2048;

    include             /etc/nginx/mime.types;
    default_type        application/octet-stream;

    log_format  main  '$remote_addr - $remote_user [$time_local] "$request" '
                      '$status $body_bytes_sent "$http_referer" '
                      '"$http_user_agent" "$http_x_forwarded_for"';

    access_log /proc/self/fd/1 main;

    log_format vhost '$host $remote_addr - $remote_user [$time_local] '
                     '"$request" $status $body_bytes_sent '
                     '"$http_referer" "$http_user_agent"';

    access_log /proc/self/fd/1 vhost;
    error_log /proc/self/fd/2;

    % if proxyprotocol:
    real_ip_header proxy_protocol;
    % endif

    # If we receive X-Real-IP, pass it through; otherwise, pass along the
    # remote addr used to connect to this server
    map $proxy_protocol_addr $proxy_x_real_ip {
      default $proxy_protocol_addr;
      ''      $remote_addr;
    }

    # If we receive $proxy_protocol_addr, pass it through
    map $proxy_protocol_addr $proxy_x_forwarded_for {
      default $proxy_protocol_addr;
      ''      $proxy_add_x_forwarded_for;
    }

    # If we receive X-Forwarded-Proto, pass it through; otherwise, pass along the
    # scheme used to connect to this server
    map $http_x_forwarded_proto $proxy_x_forwarded_proto {
      default $http_x_forwarded_proto;
      ''      $scheme;
    }

    # If we receive Upgrade, set Connection to "upgrade"; otherwise, delete any
    # Connection header that may have been passed to this server
    map $http_upgrade $proxy_connection {
      default upgrade;
      '' close;
    }

    gzip on;
    gzip_comp_level 5;
    gzip_disable "msie6";
    gzip_http_version 1.1;
    gzip_min_length 256;
    gzip_types application/atom+xml application/javascript application/json application/rss+xml application/vnd.ms-fontobject application/x-font-ttf application/x-web-app-manifest+json application/xhtml+xml application/xml font/opentype image/svg+xml image/x-icon text/css text/plain text/x-component;
    gzip_proxied any;
    gzip_vary on;

    # HTTP 1.1 support
    proxy_http_version 1.1;
    proxy_buffering off;
    proxy_set_header Host $http_host;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection $proxy_connection;
    proxy_set_header X-Real-IP $proxy_x_real_ip;
    proxy_set_header X-Forwarded-For $proxy_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $proxy_x_forwarded_proto;

    % for service in services.values():
    # ${service.name} (${service.source})
    upstream ${service.name}.${domain} {
      least_conn;
    %   for server in service.servers:
      server ${server.ip}:${server.port} weight=${server.weight};
    %   endfor
    }

    server {
      server_name_in_redirect off;
      port_in_redirect off;

      listen ${port} ${'proxy_protocol' if proxyprotocol else ''};
      server_name ${service.name}.${domain};

      location / {
        proxy_pass http://${service.name}.${domain};
      }
    }


    % endfor

    server {
        listen ${port} default_server ${'proxy_protocol' if proxyprotocol else ''};
        server_name _; # This is just an invalid value which will never trigger on a real hostname.

        location / {
            return 503;
        }

        location /_status {
            return 200;
        }
    }
}
