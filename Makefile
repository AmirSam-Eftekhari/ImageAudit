.PHONY: setup api web test lint demo
setup: ; sh scripts/dev.sh setup
api:   ; sh scripts/dev.sh api
web:   ; sh scripts/dev.sh web
test:  ; sh scripts/dev.sh test
lint:  ; sh scripts/dev.sh lint
demo:  ; sh scripts/dev.sh demo
