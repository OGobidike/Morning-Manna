

# This starts from an image that already has Python installed
FROM python:3.12-slim

# Commands run inside this folder in the container
WORKDIR /app

# Copy the dependency list and the code into the container
COPY pyproject.toml .
COPY app ./app

# Install the project and its dependencies
RUN pip install --no-cache-dir .

# Document that the app listens on this port
EXPOSE 8000

# The command that runs when the container starts
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
