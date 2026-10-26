"""Real frontend bootstrap + authenticated routes with test-only Clerk lifecycle.
Run auth_browser_server.py and isolated Chrome on debugging port 9333 first.
"""
import asyncio
import json
import urllib.request
from tests.test_editor_browser import Chrome

BASE='http://127.0.0.1:8768'
PID='d'*32
JID='a'*32

def data(path):return json.load(urllib.request.urlopen(BASE+path))
def reset():urllib.request.urlopen(urllib.request.Request(BASE+'/__auth/reset',data=b'',method='POST')).close()

async def main():
    import websockets
    target=next(t for t in json.load(urllib.request.urlopen('http://127.0.0.1:9333/json/list')) if t['type']=='page')
    async with websockets.connect(target['webSocketDebuggerUrl'],origin='http://localhost:9333',max_size=None) as ws:
        c=Chrome(ws);await c.call('Runtime.enable');await c.call('Page.enable')
        for old in json.load(urllib.request.urlopen('http://127.0.0.1:9333/json/list')):
            if old['type']=='page' and old['id']!=target['id']:await c.call('Target.closeTarget',{'targetId':old['id']})
        await c.call('Page.bringToFront')
        await c.call('Emulation.setDeviceMetricsOverride',{'width':1366,'height':1000,'deviceScaleFactor':1,'mobile':False})
        async def visit(path):
            await c.call('Page.navigate',{'url':BASE+path})
            await c.until("location.pathname==="+json.dumps(path.split('?')[0]))
        async def ready():
            await c.until("!!document.getElementById('sign-out')?.onclick&&!document.getElementById('protected-page').hidden")
        async def login():
            await c.until("location.pathname==='/login_C.html'&&document.getElementById('sign-in')?.textContent.includes('Sign in required')")
        await c.call('Page.navigate',{'url':'about:blank'});reset()
        await visit('/projects_C.html');await ready()
        assert await c.js("document.querySelectorAll('#sign-out').length===1")
        # Provider failure is retryable and is never represented as a completed logout.
        await c.js('window.failFixtureSignOut=true');await c.click('#sign-out')
        await c.until("document.getElementById('status').textContent.includes('Could not finish signing out')")
        assert data('/__auth/state')['active']
        assert await c.js("!document.getElementById('sign-out').disabled")
        await c.js('window.failFixtureSignOut=false')
        # Pending getToken must never send a settings write after sign-out begins.
        await visit('/settings_C.html');await ready()
        await c.until("document.getElementById('settings-form').onsubmit!==null")
        await c.js("window.dispatchEvent(new PageTransitionEvent('pageshow',{persisted:true}))")
        await ready()
        await c.until("document.getElementById('settings-form').onsubmit!==null")
        await c.js("window.delayFixtureToken=true;document.getElementById('settings-form').requestSubmit(document.querySelector('#settings-form button[type=submit]'))")
        await c.click('#sign-out');await login()
        assert not data('/__auth/state')['active']
        assert data('/__auth/state')['revocations']==1
        assert data('/__auth/state')['settings_posts']==0
        await c.call('Page.reload');await login()
        # A separate authenticated tab must also leave its protected view.
        reset();await visit('/projects_C.html');await ready()
        second=await c.call('Target.createTarget',{'url':BASE+'/projects_C.html'})
        targets=json.load(urllib.request.urlopen('http://127.0.0.1:9333/json/list'))
        other=next(t for t in targets if t['id']==second['targetId'])
        async with websockets.connect(other['webSocketDebuggerUrl'],origin='http://localhost:9333',max_size=None) as other_ws:
            tab=Chrome(other_ws);await tab.call('Runtime.enable');await tab.call('Page.enable')
            await tab.until("!!document.getElementById('sign-out')?.onclick&&!document.getElementById('protected-page').hidden")
            await c.call('Page.bringToFront')
            # Visit the editor so Back can return to a previously protected page.
            await visit('/editor_C.html?project='+PID+'&job='+JID+'&clip=0');await ready()
            await c.until("document.getElementById('editor-video').readyState>=2&&!document.getElementById('cap-text').disabled")
            await c.js("localStorage.setItem('cascade-prototype-v1',JSON.stringify({user:{id:'old-demo'},projects:[{id:'keep-demo'}]}));sessionStorage.setItem('unrelated','keep');document.cookie='__session=fixture-auth-token; path=/'")
            await c.input('cap-text','Draft survives sign out')
            history=await c.call('Page.getNavigationHistory');previous=history['entries'][history['currentIndex']-1]['id']
            await c.click('#sign-out');await login()
            await tab.until("location.pathname==='/login_C.html'")
            assert not data('/__auth/state')['active']
            assert data('/__auth/data')['project_preserved']
            assert data('/__auth/data')['draft']['state']['texts']['0']=='Draft survives sign out'
            assert await c.js("JSON.parse(localStorage.getItem('cascade-prototype-v1')).user===null")
            assert await c.js("JSON.parse(localStorage.getItem('cascade-prototype-v1')).projects[0].id==='keep-demo'")
            assert await c.js("Object.keys(localStorage).some(k=>k.startsWith('cascade-editor:v1:'))")
            assert await c.js("sessionStorage.getItem('unrelated')==='keep'")
            assert await c.js("!document.cookie.split(';').some(k=>k.trim().startsWith('__session='))")
            assert await c.js("fetch('/api/projects',{credentials:'same-origin'}).then(r=>r.status)")==401
            await c.call('Page.navigateToHistoryEntry',{'entryId':previous});await login()
            await c.call('Page.reload');await login()
            await visit('/projects_C.html');await login()
            assert await c.js("fetch('/api/session',{credentials:'same-origin'}).then(r=>r.status)")==401
        await c.call('Target.closeTarget',{'targetId':other['id']})
        assert not c.errors,c.errors
        print('Logout browser checks passed: awaited provider revocation, retry, delayed-token rejection, cookie cleanup, cross-tab logout, draft/project preservation, refresh, Back and direct protected-page denial.')

if __name__=='__main__':asyncio.run(main())
