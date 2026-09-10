from __future__ import annotations
import hashlib, json, time, uuid

VERSION='0.1.0'
CAMPAIGN='GA-PROMPT-OS-CONVERGENCE-001'

def compile_prompt(payload: dict | None = None) -> dict:
    payload = payload or {}
    run_id = payload.get('run_id') or f"GA-{int(time.time()*1000)}-{uuid.uuid4().hex[:6]}"
    objective = payload.get('objective') or 'Compile governed software mission'
    packet = {
        'prompt_id': payload.get('prompt_id','software.self-build'),
        'version': payload.get('version',VERSION),
        'run_id': run_id,
        'estate': 'Ghost Atlas',
        'department': payload.get('department','D01-software'),
        'campaign': payload.get('campaign',CAMPAIGN),
        'objective': objective,
        'desired_state': payload.get('desired_state',objective),
        'definition_of_done': payload.get('definition_of_done',['artifact_created','tests_pass','deployment_live','runtime_observed','proof_receipt']),
        'executive_agent':'JANUS PRIME',
        'specialist_agent':payload.get('specialist_agent','workforce-spine.autobuilder@0.1.0'),
        'context_sources':payload.get('context_sources',['.build-truth/','software-design/','Universal CaseGraph']),
        'allowed_capabilities':payload.get('allowed_capabilities',['repository.read','repository.write','test.execute','build.execute','deployment.create','runtime.observe']),
        'forbidden_capabilities':['self_authorize','self_verify','silent_promote'],
        'constraints':payload.get('constraints',['PATCH_NOT_REPLACE','INDEPENDENT_VERIFICATION']),
        'workflow':['INGEST','RECONCILE','COMPILE','AUTHORIZE','DECOMPOSE','DISPATCH','IMPLEMENT','TEST','DEPLOY','VERIFY','PROVE','WRITEBACK'],
        'execution_policy':{'autonomy':'A3','bounded':True},
        'retry_policy':{'maximum_attempts':3},
        'verification':{'independent':True,'authorities':['SECA','DevOS','Medusa']},
        'proof_class':payload.get('proof_class','P8'),
        'evidence_required':payload.get('evidence_required',['commit_sha','tests_passed','deployment_url','runtime_probe']),
        'memory_writeback':{'required':True,'authority':'Thoth'},
        'completion':{'state':'DRAFT','receipt':None,'proofgrid_id':None},
        'provenance':{'compiler':'ghost-atlas-prompt-os@0.1.0','execution_body':'VULCAN/Render'}
    }
    packet['packet_hash']=hashlib.sha256(json.dumps(packet,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return packet

def status() -> dict:
    return {'status':'PASS','service':'ghost-atlas-prompt-os','version':VERSION,'campaign':CAMPAIGN,'execution_body':'VULCAN','deployment_provider':'Render'}
