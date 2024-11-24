# Use an official Python runtime as a parent image
FROM python:3.11

# Set the working directory in the container
WORKDIR /usr/app/src

# Copy only the requirements file, to leverage Docker cache
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy the application files
COPY app.py .

# Copy the helper directory
COPY helper/ ./helper

COPY schema/ ./schema

# Copy config file
COPY config.ini .

# Specify the default command to run on container start
CMD ["python", "./app.py"]
