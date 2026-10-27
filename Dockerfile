FROM python:3.12-slim

# pymupdf e numpy tem wheel manylinux; sem compilador na imagem de proposito.
RUN pip install --no-cache-dir --upgrade pip

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY detector.py server.py ./

# Roda sem privilegio: o container nao tem nada pra escrever alem de /tmp.
RUN useradd --system --uid 10001 --no-create-home etiqueta
USER 10001

# O gunicorn tenta escrever no HOME e o rootfs e' read-only; /tmp e' tmpfs.
ENV HOME=/tmp

EXPOSE 8000
CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:8000", "--timeout", "60", "--worker-tmp-dir", "/tmp", "server:app"]
