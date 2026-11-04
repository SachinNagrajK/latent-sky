import { createClient } from 'npm:@supabase/supabase-js@2';
const cors={'Access-Control-Allow-Origin':'*','Access-Control-Allow-Headers':'authorization, apikey, content-type, x-client-info'};
Deno.serve(async req=>{
 if(req.method==='OPTIONS')return new Response('ok',{headers:cors});
 if(req.method!=='POST')return new Response('Method not allowed',{status:405,headers:cors});
 try {
 const supabase=createClient(Deno.env.get('SUPABASE_URL')!,Deno.env.get('SUPABASE_ANON_KEY')!,{global:{headers:{Authorization:req.headers.get('Authorization')||''}}});
 const {data:{user},error:authError}=await supabase.auth.getUser();
 if(authError||!user)return Response.json({error:'Sign in required'},{status:401,headers:cors});
 const body=await req.json();
 const {data,error}=await supabase.rpc('enqueue_job',{p_case:body.case_id,p_key:body.idempotency_key,p_parameters:body.parameters||{},p_kind:body.kind||'image'});
 return Response.json(error?{error:error.message}:data,{status:error?400:200,headers:cors});
 }catch{return Response.json({error:'Invalid request'},{status:400,headers:cors});}
});
