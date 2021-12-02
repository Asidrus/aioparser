build:
	docker build . --tag aioparser
remove:
	docker rmi -f aioparser
run:
	docker run \
		-d \
		--rm \
		--net=host \
		--name='aioparser' \
		-v ~/aioparser-results/:/aioparser-results/ \
		aioparser \
		bash -c \
		"python main.py"
stop:
	docker stop aioparser