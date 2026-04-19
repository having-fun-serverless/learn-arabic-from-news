FROM --platform=linux/arm64 public.ecr.aws/lambda/python:3.12

# CAMeL Tools morphology DB lives here; bundled into the image at build time.
ENV CAMELTOOLS_DATA=/opt/camel_data

COPY requirements.txt ${LAMBDA_TASK_ROOT}/requirements.txt
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt

# `light` pulls calima-msa-r13 (morphology DB used by MLEDisambiguator) without
# the ~GB-scale neural-model packages.
RUN mkdir -p ${CAMELTOOLS_DATA} && camel_data -i light

# Top-5000 Arabic lemma frequency list (Hermit Dave's FrequencyWords).
# Slim it down to a {"<lemma>": rank} JSON the handler can mmap-cheap.
RUN curl -sSL \
      https://raw.githubusercontent.com/hermitdave/FrequencyWords/master/content/2018/ar/ar_50k.txt \
      -o /tmp/ar_50k.txt \
 && python -c "import json,sys; \
lines = open('/tmp/ar_50k.txt', encoding='utf-8').read().splitlines(); \
ranks = {l.split(' ', 1)[0]: i + 1 for i, l in enumerate(lines[:5000]) if l.strip()}; \
json.dump(ranks, open('${LAMBDA_TASK_ROOT}/freq_top5000.json', 'w'), ensure_ascii=False)" \
 && rm /tmp/ar_50k.txt

COPY handler.py ${LAMBDA_TASK_ROOT}/handler.py

CMD ["handler.lambda_handler"]
