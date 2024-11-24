# Use an official Python runtime as a parent image
FROM public.ecr.aws/lambda/python:3.11

# Copy requirements.txt
COPY requirements.txt ${LAMBDA_TASK_ROOT}

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application files
COPY internet_search.py ${LAMBDA_TASK_ROOT}

# Specify the default command to run on container start
CMD [ "internet_search.lambda_handler" ]
