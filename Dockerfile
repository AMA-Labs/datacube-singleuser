FROM osgeo/gdal:ubuntu-small-3.2.2
LABEL maintainer="Riaan Stegmann(rstegmann-arch)"

ENV PYTHONUNBUFFERED=1
ENV LC_ALL C.UTF-8

ENV NB_USR=odc_admin
ENV NB_PSW=abc123
ENV DB_DATABASE=datacube
ENV DB_HOSTNAME=localhost
ENV DB_USERNAME=datacube
ENV DB_PASSWORD=supersecretpassword
ENV DB_PORT=5432
ENV DATACUBE_CONFIG_PATH=/.datacube.conf


ARG DEBIAN_FRONTEND=noninteractive
ARG ODC_VERSION=1.8.6

# Install common base image and python dependencies
RUN apt update && apt install -y --no-install-recommends \
    sudo \
    software-properties-common \
    build-essential \
    python3-pip python3-dev \
    git \
    libpq-dev \
    libgeos-dev \
    libproj-dev \
    libudunits2-dev \
    libgfortran4 \
    postgresql \
    && rm -rf /var/lib/apt/lists/* \
    && python3 -m pip install -U pip \
    # Download the wrs conversion shape file
    && mkdir -p /opt/odc/data && cd /opt/odc/data \
    && curl https://prd-wret.s3.us-west-2.amazonaws.com/assets/palladium/production/s3fs-public/atoms/files/WRS2_descending_0.zip -o wrs2_descending.zip \
    && cd - \
    # Install NodeJS
    && curl -sL https://deb.nodesource.com/setup_16.x | bash - \
    && apt install -y nodejs \
    && npm install -g configurable-http-proxy


COPY requirements.txt .

RUN pip install -r requirements.txt \    
    && rm -rf .cache/pip

RUN pip3 install \    
    GDAL==$(gdal-config --version) \
    odc-apps-dc-tools \
    --no-binary psycopg2 psycopg2 && \
    rm -rf .cache/pip    

COPY src/scripts /opt/odc/
COPY src/products /opt/odc/products
COPY src/jupyterhub_config.py /opt/jupyterhub/etc/jupyterhub/jupyterhub_config.py
COPY docker-entrypoint.sh /usr/local/bin/

RUN service postgresql start \
    && su -c "createuser --createdb --login --superuser $DB_USERNAME" postgres \
    && su -c "createdb --owner=$DB_USERNAME $DB_USERNAME" postgres \
    && export q="alter user $DB_USERNAME with password '$DB_PASSWORD';" \
    && su -c 'psql -c "$q"' postgres \
    && datacube system init

RUN chmod +x /usr/local/bin/docker-entrypoint.sh && ln -s /usr/local/bin/docker-entrypoint.sh / && hash -r 
ENTRYPOINT [ "docker-entrypoint.sh" ]

CMD [ "jupyterhub","-f", "/opt/jupyterhub/etc/jupyterhub/jupyterhub_config.py"]