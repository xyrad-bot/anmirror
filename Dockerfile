FROM clyfly/xycloud:latest

WORKDIR /usr/src/app
RUN chmod 777 /usr/src/app

RUN python3 -m venv xyenv

COPY . .

CMD ["bash", "start.sh"]
