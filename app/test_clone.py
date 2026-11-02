import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import clone_repositories as clone

class CloneTests(unittest.TestCase):
 def test_delivery_url_and_paths(self):
  with tempfile.TemporaryDirectory(prefix='source space ') as folder,patch.object(clone.subprocess,'run') as run:
   self.assertEqual(clone.run(Path(folder)/'nested destination',True,'https://github.com/iamdarshg/delivery-source.git'),0);run.assert_not_called()
   for url in ['http://github.com/iamdarshg/a','https://evil.example/a','https://github.com/other/a','https://github.com/iamdarshg/../bad','https://github.com/iamdarshg/a?x=1']:
    with self.assertRaises(ValueError):clone.run(folder,True,url)
 def test_dry_run_no_writes(self):
  with tempfile.TemporaryDirectory() as folder:
   target=Path(folder)/'absent'
   with patch.object(clone.subprocess,'run') as run:
    self.assertEqual(clone.run(target,True),0);run.assert_not_called();self.assertFalse(target.exists())
 def test_missing_git(self):
  with tempfile.TemporaryDirectory() as folder,patch.object(clone.shutil,'which',return_value=None):
   target=Path(folder)/'absent';self.assertEqual(clone.run(target),1);self.assertFalse(target.exists())
 def test_clone_fixed_commands_and_commit(self):
  with tempfile.TemporaryDirectory() as folder,patch.object(clone.shutil,'which',return_value='git'),patch.object(clone.subprocess,'run') as run,patch.object(clone.subprocess,'check_output',return_value='a'*40+'\n'):
   self.assertEqual(clone.run(folder),0);self.assertEqual(run.call_count,2)
   for call in run.call_args_list:
    args=call.args[0];self.assertIn('--no-recurse-submodules',args);self.assertIn('core.hooksPath=',args);self.assertNotIn('shell',call.kwargs)
   self.assertEqual(json.loads((Path(folder)/'clone-results.json').read_text())[0]['commit'],'a'*40)
 def test_existing_preserved(self):
  with tempfile.TemporaryDirectory() as folder,patch.object(clone.shutil,'which',return_value='git'),patch.object(clone.subprocess,'run') as run:
   for name in clone.REPOS:
    path=Path(folder)/name;path.mkdir();(path/'keep').write_text('original')
   self.assertEqual(clone.run(folder),0);run.assert_not_called()
   self.assertEqual((Path(folder)/'drone-arm/keep').read_text(),'original')
if __name__=='__main__':unittest.main()
