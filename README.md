# discarbon-poap-dispenser-api
A backend that verifies and issues POAPs via REST requests

## Development

To start developing create a virtual environment and install the requirements (regular and devlopment) files:
```
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -r requirements_dev.txt
```

### Enable pre-commit (optional)

`pre-commmit` is used to perform some lint checks upon commit and push. Enable `pre-commit` with:
```
pre-commit install
```

## Running the service

### Without Docker

Run the service locally via uvicorn with:
```
uvicorn app.main:poap_api --log-config=logging.yaml --reload
```

If testing the service locally with an SSL-enabled site (https), first generate an SSL certificate in order to start uvicorn with https:
```
apt install openssl
openssl genrsa -des3 -out myCA.key 2048
openssl req -x509 -new -nodes -key myCA.key -sha256 -days 1825 -out myCA.pem
```
then provide these to uvicorn:
```
sudo uvicorn app.main:poap_api --log-config=logging.yaml --reload --ssl-certfile=myCA.pem --ssl-keyfile=myCA.key
```
