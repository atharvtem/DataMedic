FROM postgres:16
COPY --chmod=0644 docker/init-db.sh /docker-entrypoint-initdb.d/init-db.sh
