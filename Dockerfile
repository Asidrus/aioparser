FROM continuumio/miniconda3
ARG path=/app
ARG PROJECT='project'
WORKDIR $path/$PROJECT
RUN mkdir -m 777 /aioparser-results
COPY req.yml ./
RUN conda env create -f req.yml
RUN echo "source activate $PROJECT" > ~/.bashrc
ENV PATH /opt/conda/envs/aioparser/bin:$PATH
COPY . .

