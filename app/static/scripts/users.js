const status=document.getElementById('users-status'),list=document.getElementById('users-list'),form=document.getElementById('create-user');
let currentUsername='';
async function request(url,options={}){
  const response=await fetch(url,options);
  const body=await response.json();
  if(!response.ok)throw new Error(typeof body.detail==='string'?body.detail:'Check the entered account details.');
  return body;
}
async function loadUsers(){
  const users=await request('/api/admin/users');
  list.replaceChildren();
  document.getElementById("user-count").textContent=`${users.length} account${users.length===1?"":"s"}`;
  for(const user of users){
    const row=document.createElement('tr');
    for(const value of [user.display_name,user.username,user.role==='admin'?'Admin':'User',user.enabled?'Enabled':'Disabled']){
      const cell=document.createElement('td');cell.textContent=value;row.append(cell);
    }
    const actions=document.createElement('td');
    if(user.managed&&user.username.toLowerCase()!==currentUsername.toLowerCase()){
      const edit=document.createElement('button');edit.type='button';edit.className='secondary edit-user';
      edit.setAttribute('aria-label',`Edit ${user.username}`);edit.title=`Edit ${user.username}`;
      edit.innerHTML='<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="m16 3 5 5-12 12-6 1 1-6Z"/><path d="m14 5 5 5"/></svg>';
      edit.onclick=()=>{if(!saving)editUser(user)};
      const remove=document.createElement('button');remove.type='button';remove.className='secondary delete-user';
      remove.setAttribute('aria-label',`Delete ${user.username}`);remove.title=`Delete ${user.username}`;
      remove.innerHTML='<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7M14 10v7"/></svg>';
      remove.onclick=async()=>{
        if(saving||!window.confirm(`Delete ${user.display_name} (${user.username})? Their account and application access will be removed.`))return;
        saving=true;remove.disabled=edit.disabled=true;for(const element of form.elements)element.disabled=true;
        try{
          await request(`/api/admin/users/${encodeURIComponent(user.username)}`,{method:'DELETE'});
          if(editingUsername===user.username)resetEditor();
          status.textContent=`Deleted ${user.username}. Application access has been removed.`;
          await loadUsers();
        }catch(error){status.textContent=error.message;remove.disabled=edit.disabled=false;}
        finally{saving=false;for(const element of form.elements)element.disabled=false;}
      };
      const controls=document.createElement('div');controls.className='user-row-actions';controls.append(edit,remove);actions.append(controls);
    }else actions.textContent=user.managed?'Your account':'Initial admin';
    row.append(actions);list.append(row);
  }
}
let editingUsername=null,saving=false;
const submitButton=document.getElementById('save-user'),cancelEdit=document.getElementById('cancel-edit');
function resetEditor(){
  editingUsername=null;form.reset();form.elements.username.readOnly=false;
  form.elements.password.required=true;document.getElementById('create-title').textContent='Create user';
  document.getElementById('password-help').textContent='At least 12 characters. Share with the user securely.';
  submitButton.textContent='Create user';cancelEdit.classList.add('hidden');
}
function editUser(user){
  resetEditor();editingUsername=user.username;
  const parts=user.display_name.split(' ');
  form.elements.first_name.value=user.first_name??parts.shift();
  form.elements.last_name.value=user.last_name??parts.join(' ');
  form.elements.username.value=user.username;form.elements.username.readOnly=true;
  form.elements.role.value=user.role;form.elements.enabled.value=String(Boolean(user.enabled));
  form.elements.password.required=false;
  document.getElementById('password-help').textContent='Leave blank to keep the current password, or enter a new password of at least 12 characters.';
  document.getElementById('create-title').textContent=`Edit user · ${user.username}`;
  submitButton.textContent='Update user';cancelEdit.classList.remove('hidden');
  status.textContent=`Editing ${user.username}. Username cannot be changed.`;
  form.scrollIntoView({block:'center',behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'});
  form.elements.first_name.focus({preventScroll:true});
}
cancelEdit.onclick=()=>{if(!saving){resetEditor();status.textContent='Editing cancelled.'}};
form.onsubmit=async event=>{
  event.preventDefault();if(saving)return;
  const username=editingUsername;
  const data=Object.fromEntries(new FormData(form));data.enabled=data.enabled==='true';
  if(username){delete data.username;if(!data.password)delete data.password}
  saving=true;for(const element of form.elements)element.disabled=true;
  try{
    const user=await request(username?`/api/admin/users/${encodeURIComponent(username)}`:'/api/admin/users',{method:username?'PATCH':'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
    resetEditor();status.textContent=`${username?'Updated':'Created'} ${user.username} as ${user.role}. Access is ${user.enabled?'enabled':'disabled'}.${username?' Existing sessions revoked.':''}`;
    await loadUsers();
  }catch(error){status.textContent=error.message;}finally{saving=false;for(const element of form.elements)element.disabled=false;}
};
(async()=>{try{const profile=await request('/api/auth/profile');currentUsername=profile.username;showProfile(profile);await loadUsers();}catch(error){status.textContent=error.message;form.querySelector('button').disabled=true;}})();

function showProfile(profile){
  document.getElementById('profile-name').textContent=profile.display_name;
  document.getElementById('profile-role').textContent='Administrator';
  const icon='<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M12 3 4 6v6c0 5 8 9 8 9s8-4 8-9V6z"/><circle cx="12" cy="10" r="2.5"/><path d="M8 16c0-4 8-4 8 0"/></svg>';
  for(const id of ['profile-toggle','profile-avatar'])document.getElementById(id).innerHTML=icon;
  document.getElementById('profile-toggle').setAttribute('aria-label',`Open profile menu for ${profile.display_name} (Administrator)`);
}
const profileToggle=document.getElementById('profile-toggle'),profilePanel=document.getElementById('profile-panel');
function closeProfile(){profilePanel.classList.add('hidden');profileToggle.setAttribute('aria-expanded','false')}
profileToggle.onclick=()=>{const open=profilePanel.classList.toggle('hidden')===false;profileToggle.setAttribute('aria-expanded',String(open))};
document.addEventListener('click',event=>{if(!event.target.closest('.profile-menu'))closeProfile()});
document.addEventListener('keydown',event=>{if(event.key==='Escape'&&!profilePanel.classList.contains('hidden')){closeProfile();profileToggle.focus()}});
