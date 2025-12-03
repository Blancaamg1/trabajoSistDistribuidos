
media: portal2-ost.zip
	mkdir -p media
	unzip -o $< -d media

portal2-ost.zip:
	wget http://media.steampowered.com/apps/portal2/soundtrack/Portal2-OST-Complete.zip -O $@

.PHONY: test
test:
	pytest -v test

run-server:
	./media_server.py server.config

run-render:
	./media_render.py render.config

clean:
	$(RM) -r spotifice*.py *.zip .pytest_cache __pycache__ test/__pycache__
