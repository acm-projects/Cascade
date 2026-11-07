/* Account/project scoped selection shared by canvas and Exports. */
window.CascadeExportSelection = {
  key(user, project) {return 'cascade-export-selection:v1:'+user+':'+project;},
  read(user,project) {
    try {
      const rows=JSON.parse(localStorage.getItem(this.key(user,project))) || [];
      if(!Array.isArray(rows))return [];
      const seen=new Set();
      return rows.filter(e=>e&&/^[a-f0-9]{32}$/.test(e.job_id)&&Number.isInteger(e.clip_index)&&e.clip_index>=0).filter(e=>{const key=e.job_id+':'+e.clip_index;if(seen.has(key))return false;seen.add(key);return true;});
    }catch{return [];}
  },
  write(user,project,entries) {localStorage.setItem(this.key(user,project),JSON.stringify(entries));}
};
