FROM continuumio/miniconda3
WORKDIR /home/tester/aioparser
EXPOSE $PORT
RUN mkdir -m 777 /home/tester/aioparser-results
COPY req.yml ./
RUN conda env create -f req.yml
RUN echo "source activate aioparser" > ~/.bashrc
ENV PATH /opt/conda/envs/aioparser/bin:$PATH
COPY . .

