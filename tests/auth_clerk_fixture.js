/* Test provider only: mirror Clerk’s transient undefined state, callback and default redirect. */
(()=>{
  const listeners=new Set();
  const user={id:'auth-fixture-user',fullName:'Auth fixture'};
  const session={id:'fixture-session',getToken:async()=>{if(window.delayFixtureToken)await new Promise(resolve=>setTimeout(resolve,400));return 'fixture-auth-token';}};
  window.Clerk={user:null,session:null,
    async load(){const data=await(await fetch('/__auth/state')).json();this.user=data.active?user:null;this.session=data.active?session:null;},
    addListener(fn){listeners.add(fn);fn({user:this.user,session:this.session});return()=>listeners.delete(fn);},
    async signOut(callbackOrOptions){
      if(window.failFixtureSignOut)throw Error("Fixture provider unavailable");
      this.user=undefined;this.session=undefined;
      for(const fn of listeners)fn({user:undefined,session:undefined});
      await new Promise(resolve=>setTimeout(resolve,250));
      await fetch('/__auth/revoke',{method:'POST'});
      if(typeof callbackOrOptions==='function')await callbackOrOptions();
      else {location.assign(callbackOrOptions?.redirectUrl || '/');return;}
      this.user=null;this.session=null;
      for(const fn of listeners)fn({user:null,session:null});
    },
    mountSignIn(node){node.textContent='Sign in required (fixture)';},openUserProfile(){}
  };
})();
