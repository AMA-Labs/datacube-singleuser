FROM osgeo/gdal:ubuntu-small-3.2.2
LABEL maintainer="Riaan Stegmann(rstegmann-arch)"

ENV HOME="/root"
ENV PYTHONUNBUFFERED=1
ENV LC_ALL C.UTF-8

ENV DB_DATABASE=datacube
ENV DB_HOSTNAME=db
ENV DB_USERNAME=datacube
ENV DB_PASSWORD=supersecretpassword
ENV DB_PORT=5432


ARG DEBIAN_FRONTEND=noninteractive
ARG ODC_VERSION=1.8.6

WORKDIR $HOME

# Install common base image and python dependencies
RUN apt update && apt install -y --no-install-recommends \
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
    && python3 -m pip install -U pip

COPY ./requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt \    
    && rm -rf $HOME/.cache/pip

RUN pip3 install --no-cache-dir \    
    GDAL==$(gdal-config --version) \
    odc-apps-dc-tools \
    --no-binary psycopg2 psycopg2 && \
    rm -rf $HOME/.cache/pip    

COPY src/scripts /opt/odc/
COPY src/products /opt/odc/products
COPY docker-entrypoint.sh /usr/local/bin/

RUN chmod +x /usr/local/bin/docker-entrypoint.sh && ln -s /usr/local/bin/docker-entrypoint.sh / && hash -r 
ENTRYPOINT [ "docker-entrypoint.sh" ]
CMD [ "datacube" ]