# lab-integrator-service

Integrador HL7 (ORM/ORU) con MLLP, File watcher, y mapeo YAML.

## Requisitos
- Python 3.12+
- pip, virtualenv

## Setup
```bash
python -m venv .venv
source .venv/bin/activate

## Instalar dependencias
### Producción
pip install -r requirements.txt

### Desarrollo
pip install -r requirements-dev.txt

pre-commit install
