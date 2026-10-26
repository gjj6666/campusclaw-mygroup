"""Shared page assets without a browser build step."""
from pathlib import Path


def asset(name):
    return Path(__file__).with_name('static').joinpath(name).read_text(encoding='utf-8')


def head(title):
    return ('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1"><title>' + title + '</title>'
            '<script>' + asset('theme.js') + '</script><style>' + asset('warm.css') + '\n' + asset('workspace.css') + '</style></head>')


def dialog():
    return '<dialog id="dialog" aria-labelledby="dialog-title"><div class="dialog-head"><h2 id="dialog-title"></h2><button id="dialog-close" class="secondary" aria-label="关闭弹窗" type="button">关闭</button></div><div id="dialog-body"></div></dialog>'


def scripts(*names):
    return ''.join('<script>' + asset(name) + '</script>' for name in ('ui.js', *names)) + '</body></html>'
