FROM openjdk:11-jdk-slim

# Install required packages
RUN apt-get update && apt-get install -y \
    curl \
    wget \
    unzip \
    python3 \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

# Install AWS CLI
RUN pip3 install awscli

# Install JMeter
ENV JMETER_VERSION=5.6.3
ENV JMETER_HOME=/opt/apache-jmeter-${JMETER_VERSION}
ENV JMETER_BIN=${JMETER_HOME}/bin
ENV PATH=${JMETER_BIN}:${PATH}

RUN wget https://archive.apache.org/dist/jmeter/binaries/apache-jmeter-${JMETER_VERSION}.tgz \
    && tar -xzf apache-jmeter-${JMETER_VERSION}.tgz -C /opt \
    && rm apache-jmeter-${JMETER_VERSION}.tgz

# Add JMeter plugins for better reporting
RUN wget https://repo1.maven.org/maven2/kg/apc/jmeter-plugins-manager/1.10/jmeter-plugins-manager-1.10.jar \
    && mv jmeter-plugins-manager-1.10.jar ${JMETER_HOME}/lib/ext/

# Create working directory
WORKDIR /jmeter

# Copy scripts
COPY run-test.sh /jmeter/
COPY jmeter.properties ${JMETER_HOME}/bin/
RUN chmod +x /jmeter/run-test.sh

# Set environment variables
ENV S3_BUCKET=""
ENV SESSION_ID=""
ENV TARGET_HOST="localhost"
ENV TARGET_PORT="8080"

# Default command
CMD ["/jmeter/run-test.sh"]