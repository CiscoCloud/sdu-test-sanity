FROM python:2.7

ENV DEBIAN_FRONTEND="noninteractive"

RUN apt-get update && \
    apt-get install -qy build-essential python-dev libxslt1-dev libxml2-dev libldap-dev libsasl2-dev && \
    rm -rf /var/lib/apt/lists/*

RUN adduser --system --group sanity
RUN mkdir /run/sanity && chown sanity:sanity /run/sanity

RUN virtualenv /venv
ENV VIRTUAL_ENV /venv
ENV PATH $VIRTUAL_ENV/bin:$PATH

RUN pip install -U pbr requests urllib3 dumb-init

WORKDIR /app
COPY requirements.txt /app/
RUN pip install -r requirements.txt

COPY . /app
RUN cd /app && pip install -e .

USER sanity
# This should probably happen in a wrapper script during run
# so it isn't baked into the image.
RUN ssh-keygen -q -t rsa -f ~/.ssh/id_rsa -N ''
WORKDIR /run/sanity
ENTRYPOINT ["/venv/bin/dumb-init", "--", "sanity"]
