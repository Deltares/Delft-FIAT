FROM fedora:44 AS base

# Input arguments
ARG PIXIENV
ARG UID=1000

# Install some handy packages and build dependencies
RUN dnf check-update && dnf -y update \
  && dnf -y install curl gcc g++ vim

# Set the user and the home directory
RUN useradd deltares
RUN usermod -u ${UID} deltares
USER deltares
WORKDIR /home/deltares

# Install pixi and copy the project meta and code
RUN curl -fsSL https://pixi.sh/install.sh | bash
ENV PATH=/home/deltares/.pixi/bin:$PATH
COPY pixi.lock pyproject.toml README.md ./
COPY --chown=deltares:deltares src/fiat ./src/fiat

# Install pixi environment
RUN chmod u+x src/ \
  && pixi install -e ${PIXIENV} \
  && rm -rf .cache \
  && find .pixi -type f -name "*.pyc" -delete

# Workaround: write a file that runs pixi with correct environment.
# This is needed because the argument is not passed to the entrypoint.
ENV RUNENV="${PIXIENV}"
RUN echo "pixi run --locked -e ${RUNENV} \$@" > run_pixi.sh \
  && chown deltares:deltares run_pixi.sh \
  && chmod u+x run_pixi.sh
ENTRYPOINT ["bash", "run_pixi.sh"]
CMD ["fiat"]
