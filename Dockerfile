FROM debian:bookworm-slim AS base
ARG PIXIENV
ARG UID=1000
RUN apt-get update && apt-get install -y curl && apt-get install -y vim && apt-get install -y binutils

RUN useradd deltares
RUN usermod -u ${UID} deltares
USER deltares
WORKDIR /home/deltares

RUN curl -fsSL https://pixi.sh/install.sh | bash
ENV PATH=/home/deltares/.pixi/bin:$PATH
COPY pixi.toml pyproject.toml README.md ./
COPY --chown=deltares:deltares src/fiat ./src/fiat

RUN chmod u+x src/ \
  && pixi run -e ${PIXIENV} install-fiat \
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
