'use strict';
document.querySelectorAll('form').forEach(form=>form.addEventListener('submit',()=>{const button=form.querySelector('button:not([type="button"])');if(button){button.disabled=true;setTimeout(()=>button.disabled=false,5000);}}));
const search=document.getElementById('admin-search');if(search)search.addEventListener('input',()=>{const term=search.value.toLowerCase();document.querySelectorAll('tbody tr,table tr').forEach(row=>{if(row.querySelector('td'))row.hidden=!row.textContent.toLowerCase().includes(term);});});
