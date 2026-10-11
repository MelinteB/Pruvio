"""Generate the React bill service from the installed business code, without altering it."""
import ast

def generate(source):
    tree=ast.parse(source);rows=source.splitlines(keepends=True);edits=[]
    for name,kind in [('close_split_bill_session','split_settled'),('reopen_split_bill_session','split_reopened')]:
        fn=next((n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name),None)
        if not fn:raise ValueError(f'Missing business function: {name}')
        commits=[n for n in fn.body if isinstance(n,ast.Expr) and isinstance(n.value,ast.Call) and isinstance(n.value.func,ast.Attribute) and ast.unparse(n.value.func)=='db.commit']
        if len(commits)!=1:raise ValueError(f'Unexpected transaction structure in {name}; current source needs review.')
        for node in fn.body:
            text=ast.get_source_segment(source,node) or ''
            if isinstance(node,ast.ImportFrom) and node.module=='app.services.push_service':
                if any(a.name not in ('bill_event','notify_split_transition') for a in node.names):raise ValueError('Unknown transition event import.')
                edits.append((node.lineno-1,node.end_lineno,''))
            elif isinstance(node,ast.Expr) and isinstance(node.value,ast.Call) and isinstance(node.value.func,ast.Name) and node.value.func.id in ('bill_event','notify_split_transition'):
                edits.append((node.lineno-1,node.end_lineno,''))
            elif 'enqueue(' in text or 'notify_split_transition(' in text or 'bill_event(' in text:raise ValueError('Unknown split event mechanism; refusing duplicate notifications.')
        commit=commits[0];edits.append((commit.lineno-1,commit.lineno-1,f"    from app.react_app.events import enqueue_transition\n    enqueue_transition(db, session, owner_user_id, '{kind}')\n"))
    for start,end,text in sorted(edits,reverse=True):rows[start:end]=[text]
    result='"""Generated from installed Pruvs business service. React transition events are atomic."""\n'+''.join(rows)
    ast.parse(result);return result


if __name__=='__main__':
    import argparse
    from pathlib import Path
    parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');args=parser.parse_args()
    backend=Path(__file__).resolve().parents[1]
    target=backend/'app/react_app/bill_service.py'
    result=generate((backend/'app/services/split_bill_session_service.py').read_text(encoding='utf-8'))
    if args.check:
        if not target.is_file() or target.read_text(encoding='utf-8')!=result:raise SystemExit('React bill service is stale. Run python scripts/sync_react_business.py and commit app/react_app/bill_service.py.')
        print('React bill service matches the installed business code.')
    else:
        target.write_text(result,encoding='utf-8');print('React bill service synchronized.')
