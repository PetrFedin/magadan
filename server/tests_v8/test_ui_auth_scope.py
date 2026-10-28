"""UI structural regression: claims workspace must not leak outside signed-in lab."""
from html.parser import HTMLParser
from pathlib import Path
import re

class Tree(HTMLParser):
    def __init__(self):super().__init__();self.stack=[];self.ancestors={}
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs);node=attrs.get('id')
        if node:self.ancestors[node]=tuple(self.stack)
        if tag not in {'meta','input','link','img','source','hr','br','wbr'}:
            self.stack.append((tag,node,'hidden' in attrs))
    def handle_endtag(self,tag):
        # all div/section tags are properly balanced in the authored document
        if self.stack and self.stack[-1][0]==tag:self.stack.pop()
        else:
            for i in range(len(self.stack)-1,-1,-1):
                if self.stack[i][0]==tag:
                    self.stack=self.stack[:i];break


def test_sensitive_workspaces_remain_inside_authenticated_lab():
    root=Path(__file__).resolve().parents[1]/'ui'
    html=(root/'index.html').read_text()
    t=Tree();t.feed(html)
    for name in ('benefit-v79-workspace','boundary-v8-workspace'):
        assert any(x[1]=='lab' and x[2] for x in t.ancestors[name]),name
    assert len(re.findall(r'id="[^"]+"',html))==len(set(re.findall(r'id="([^"]+)"',html)))


def test_v8_ui_has_actual_client_hooks():
    root=Path(__file__).resolve().parents[1]/'ui'
    script=(root/'ui.js').read_text()
    for key in ('refreshV8','boundary-audit','v8-mv-quality','boundary-overlaps','boundary-asset-assignments'):
        assert key in script
