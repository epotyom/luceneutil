# Run luceneutil nightly test script locally

## Purpose

Documenting steps I took to run upstream Lucene nightly benchmarks on local machine. The goal is to make it work somehow to be able to test changes in the nightly script. We can find correct/long term solutions later, so that ideally users can run nightlies out of the box.

Long term plan is to update init script/merge patches so that nightly script works out of box

## Requirements

Linux machine with 450 GB for lucene workspace, TK: CPU/RAM

## Env vars

Below is what works for me, make sure the paths exist on your machine

```
export JAVA_HOME=/usr/lib/jvm/java-25-amazon-corretto
LUCENE_BENCH_HOME=~/workspace/lucene
```

## Follow the main README to run local benchmarks

Just to make sure everything works until this point

```
...
python3 src/python/localrun.py -source wikimediumall
```

## Nightly run

### Prepare

####  Checkout lucene to trunk.nightly folder

If you have folder for baseline you can just make symlink


```
ln -s $LUCENE_BENCH_HOME/lucene_baseline $LUCENE_BENCH_HOME/trunk.nightly
```


Make sure the changes in the branch are commited, otherwise you'll get


```
    raise RuntimeError(f"lucene clone {LUCENE_CHECKOUT} is git-dirty")
RuntimeError: lucene clone /l/trunk.nightly is git-dirty
```

#### Download initial files (can take a while)

```
python3 src/python/initial_setup.py -download

xz -d enwiki-20120502-lines-1k-fixed-utf8-with-random-label.txt.lzma
```



#### Create root /l folder

some tests like KNN use `/l` folder, not sure why, maybe to make path shorter? In any case it seems easier to create one rather than figure out why:

```
sudo ln -s ~/ws/upstream_lucene /l
```

#### Data for NAD facets

Read `src/main/perf/facets/README.md` for step by step guide.
**Note**, NAD_r8 doesn't seem to be available anymore, so I downloaded r19 instead and changed generateNADTaxonomies.py to use the new file name, see code branch below.


```
cd $LUCENE_BENCH_HOME/data
wget https://nationaladdressdata.s3.amazonaws.com/NAD_r19_TXT.zip

cd $LUCENE_BENCH_HOME/util/src/python
python3 generateNADTaxonomies.py
```

#### Generate vector files

First need to install `sentence-transformers` python lib, **on MAC** it seems to be easier to use python virtual env


```
python3 -m venv luceneutil-venv
./luceneutil-venv/bin/pip3 install sentence-transformers
```

now change infer_token_vectors.py run in gradle.knn to use `./luceneutil-venv/bin/python3` instead of `python` (or create temporary python alias?)

On Linux you just need `pip3 install -U sentence-transformers` , but you might see some weird dependency installation issues, in my case I saw:

* pip3 uses old python 3.7 - had to install new pythons, see https://docs.hub.amazon.dev/languages/python/
* numpy needs gcc10 - see https://sage.amazon.dev/posts/1987865?t=7

Now run


```
./gradlew vectors-mpnet
```


Note that if this command freezes it might mean that the URLs it requests are restricted by the US law to access from the country you are in, so just move to some other country and retry

#### GEO tests data

```

cd $LUCENE_BENCH_HOME/data
wget http://download.geonames.org/export/dump/allCountries.zip
unzip allCountries.zip

```

#### Set certificate paths for github requests

```
export REQUESTS_CA_BUNDLE=/etc/pki/tls/certs/ca-bundle.crt
export SSL_CERT_FILE=/etc/pki/tls/certs/ca-bundle.crt
```

#### Make some folders nightly scripts require

```
mkdir $LUCENE_BENCH_HOME/reports.nightly
mkdir $LUCENE_BENCH_HOME/nightly_logs
mkdir -p /l/lucenenightly/docs/
```

#### dygraph-combined-dev.js

this js is used for interactive graphs, just need to download it

```
wget https://dygraphs.com/1.1.1/dygraph-combined-dev.js -P $LUCENE_BENCH_HOME/reports.nightly

```

#### Install gnuplot 6.0

gnuplot 6.0 is required for vmstats graphs. While in general you can install it using apt/yum depending on your repository, I only had 4.6 available there, so I installed from source instead.

```
cd /tmp
wget https://sourceforge.net/projects/gnuplot/files/gnuplot/6.0.4/gnuplot-6.0.4.tar.gz
tar -xzf  gnuplot-6.0.4.tar.gz
cd gnuplot-6.0.4
./configure --prefix=$HOME/local --without-x --without-cairo
make -j4
make install

### fix path
export PATH=$HOME/local/bin:$PATH
echo 'export PATH=$HOME/local/bin:$PATH' >> ~/.zshrc

### Make sure it has -c option !!!
gnuplot -h

```

#### Patch

Apply https://github.com/mikemccand/luceneutil/compare/main...epotyom:luceneutil:fix_nightly_start_from_scratch that fixes some minor bugs/adds some constants

TK: I made some of these changes in my local branch in August, maybe some issues were already fixed upstream?

**NB!** make sure your utils git repo changes are commited ('git diff' is empty), otherwise you can get


```
  File "./util/src/python/runNightlyKnn.py", line 608, in _run
    raise RuntimeError(f"luceneutil clone {constants.BENCH_BASE_DIR} is git-dirty")
RuntimeError: luceneutil clone ./util is git-dirty
```

#### Run

Note: I had to remove top log every time otherwise run fails - I think you don’t have to do it if previous run was successful?

```
rm $LUCENE_BENCH_HOME/logs/nightly.top.log
python3 src/python/nightlyBench.py -run -reset
```

It takes some time, so be patient, and if you get any errors make sure you finished all the steps above. If you still see an error - checkout [Errors fixed](https://quip-amazon.com/Zs8EAuGbj42y#temp:C:VaI269dda831c2c4e5d83a92fae9) section, maybe there is fix already.

Note that `-reset` seem to disable some tests - but I needed for the first run (TBH don’t remember why)

You can also try using `-debug` option, but it requires slightly different paths and I’ve never tested it; instead I temporarily changed some parameters/order of tests for debugging.

## Errors fixed

I’ve fixed first errors I encountered without documenting, but later I found it is useful to write down the problem and the fix, as well as create separate commit for each problem in the code branch above.

### Github ssl cert

Error

```
ssl.SSLCertVerificationError: [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate (_ssl.c:1010)
```

Fix: set env variables for python

```
export REQUESTS_CA_BUNDLE=/etc/pki/tls/certs/ca-bundle.crt
export SSL_CERT_FILE=/etc/pki/tls/certs/ca-bundle.crt
```

### Cohere

Error


```
Traceback (most recent call last):
  File "./util/src/python/nightlyBench.py", line 603, in run
    runNightlyKnn.run(runLogDir)
  File "./util/src/python/runNightlyKnn.py", line 585, in run
    return _run(results_dir)
           ^^^^^^^^^^^^^^^^^
  File "./util/src/python/runNightlyKnn.py", line 671, in _run
    knnPerfTest.smell_vectors(VECTORS_DIM, INDEX_VECTORS_FILE, True)
  File "./util/src/python/knnPerfTest.py", line 161, in smell_vectors
    size_bytes = os.path.getsize(file_name)
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "<frozen genericpath>", line 62, in getsize
FileNotFoundError: [Errno 2] No such file or directory: '/big/cohere-v3-wikipedia-en-scattered-1024d.docs.vec'
```


Fix

WiP: I’m trying to use use small vectors instead for local run. Make sure this patch was applied


```
diff --git a/src/python/runNightlyKnn.py b/src/python/runNightlyKnn.py
index 87005194..a8f19386 100644
--- a/src/python/runNightlyKnn.py
+++ b/src/python/runNightlyKnn.py
@@ -39,8 +39,8 @@ import knnPerfTest
 # VECTORS_DIM =  768

 # Cohere v3, switched Dec 7 2025:
-INDEX_VECTORS_FILE = "/big/cohere-v3-wikipedia-en-scattered-1024d.docs.vec"
-SEARCH_VECTORS_FILE = "/lucenedata/enwiki/cohere-v3/cohere-v3-wikipedia-en-scattered-1024d.queries.vec"
+INDEX_VECTORS_FILE = "/l/data/cohere-v3-wikipedia-en-scattered-1024d.docs.first1M.vec"
+SEARCH_VECTORS_FILE = "/l/data/cohere-v3-wikipedia-en-scattered-1024d.queries.first200K.vec"
 VECTORS_DIM = 1024

 VECTORS_ENCODING = "float32"
```

TK: move to the section above once the fix works

Other option: trying to use load_cohere_v3.py
Hmm I don’t think load_cohere_v3.py actually creates the file we need even though the script is mentioned in the md file.

Apply git patch first to download files


```
diff --git a/src/python/load_cohere_v3.py b/src/python/load_cohere_v3.py
index 25fddf27..8bdc33fc 100644
--- a/src/python/load_cohere_v3.py
+++ b/src/python/load_cohere_v3.py
@@ -44,7 +44,7 @@ STOP_AT = None

 LANG = "en"

-DO_INIT_LOAD = False
+DO_INIT_LOAD = True
 DO_SHUFFLE = False
 DO_PARTITION = False
 DO_SHUFFLE_ENTIRELY = False
@@ -171,7 +171,7 @@ def main():
       cur_wiki_id = None

       next_print_time_sec = start_time_sec
-      with open(csv_source_file, "w", newlines="") as meta_out, open(vec_source_file, "wb") as vec_out:
+      with open(csv_source_file, "w", newline="") as meta_out, open(vec_source_file, "wb") as vec_out:
         meta_csv_out = csv.writer(meta_out, lineterminator="\n")
         meta_csv_out.writerow(headers)
         for doc in docs:
```




```
# I had to use older versions as my linux repo doesn't have up to date Arrow
pip install pyarrow==18.1.0
pip install "pyarrow>=17.0.0,<19.0.0" datasets

sudo mkdir /b3
sudo mkdir /b2
#sudo mkdir /lucenedata
sudo chown epotyom:amazon /b3/take2
sudo chown epotyom:amazon /b2/coherev3
#sudo chown epotyom:amazon /lucenedata
mkdir -p /b3/take2
mkdir -p /b2/coherev3
#mkdir -p /lucenedata/enwiki/cohere-v3


python src/python/load_cohere_v3.py

It fails with
FileNotFoundError: [Errno 2] No such file or directory: '/lucenedata/enwiki/cohere-v3/init.csv'
but I don't think we actually need these files, just switch DO_INIT_LOAD back to False and rerun

TK:
# I don't think we need these hge files for anything???
rm -rf /lucenedata/enwiki/cohere-v3/init*


cp /b3/take2/cohere-wikipedia-v3.csv /lucenedata/enwiki/cohere-v3/init.csv
cp /b3/take2/cohere-wikipedia-v3.vec /lucenedata/enwiki/cohere-v3/init.vec
chmod 444 /lucenedata/enwiki/cohere-v3/init.csv
chmod 444 /lucenedata/enwiki/cohere-v3/init.vec

```

### runNightlyKNN KeyError no

error

```
Nightly KNN benchy failed; ignoring:
Traceback (most recent call last):
  File "./util/src/python/nightlyBench.py", line 606, in run
    runNightlyKnn.write_graph()
  File "./util/src/python/runNightlyKnn.py", line 363, in write_graph
    (series["no"], series["no.force_merge"], series["7 bits"], series["7 bits.force_merge"], series["4 bits"], series["4 bits.force_merge"]),
     ~~~~~~^^^^^^
KeyError: 'no'
```

fix: constants.NIGHTLY_LOG_DIR has to match constants.LOGS_DIR as runNightlyKNN.py uses both of them. Fixed in the code branch

### UnboundLocalError: cannot access local variable 'tasksWindownMS'

Stacktrace

```
Traceback (most recent call last):
  File "./util/src/python/nightlyBench.py", line 2094, in <module>
    run()
  File "./util/src/python/nightlyBench.py", line 710, in run
    results, cmpDiffs, searchHeaps = r.simpleReport(resultsPrev, resultsNow, False, True, "prev", "now", writer=output.append)
                                     ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "./util/src/python/benchUtil.py", line 1403, in simpleReport
    baseRawResults, heapBase, ignore, baseAvgCpuCores = parseResults(baseLogFiles)
                                                        ^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "./util/src/python/benchUtil.py", line 677, in parseResults
    return taskIters, heaps, tasksWindownMS, avgCPUCores
                             ^^^^^^^^^^^^^^
UnboundLocalError: cannot access local variable 'tasksWindownMS' where it is not associated with a value
Traceback (most recent call last):
```

Fix

Looks like the problem is there are no previous results. if DEBUG is true, we ignore it, but to minimize changes I’ve made temporary change to allow that in non-debug mode as well


```
diff --git a/src/python/nightlyBench.py b/src/python/nightlyBench.py
index 5128743e..0194456d 100644
--- a/src/python/nightlyBench.py
+++ b/src/python/nightlyBench.py
@@ -702,7 +702,8 @@ def run():
     if os.path.exists(prevFName):
       resultsPrev.append(prevFName)

-  if len(resultsPrev) == 0 and DEBUG:
+  #if len(resultsPrev) == 0 and DEBUG:
+  if len(resultsPrev) == 0:
     # sidestep exception when we can't find any previous results because DEBUG
     resultsPrev = resultsNow


```

### Gnuplot is not installed

Stacktrace


```
generate vmstat pretties
  ./reports.nightly/2026.01.05.18.26.25/fastIndexBigDocs
Traceback (most recent call last):
  File "./util/src/python/nightlyBench.py", line 2095, in <module>
    run()
  File "./util/src/python/nightlyBench.py", line 728, in run
    shutil.copy("/usr/share/gnuplot/6.0/js/gnuplot_svg.js", subDirName)
  File "/local/home/epotyom/.local/share/mise/installs/python/3.12.12/lib/python3.12/shutil.py", line 435, in copy
    copyfile(src, dst, follow_symlinks=follow_symlinks)
  File "/local/home/epotyom/.local/share/mise/installs/python/3.12.12/lib/python3.12/shutil.py", line 260, in copyfile
    with open(src, 'rb') as fsrc:
         ^^^^^^^^^^^^^^^
FileNotFoundError: [Errno 2] No such file or directory: '/usr/share/gnuplot/6.0/js/gnuplot_svg.js'
```

Fix

`gnuplot_svg.js` is already in the utils git, and it is up to date, so we just need to change the path, added commit


```
diff --git a/src/python/nightlyBench.py b/src/python/nightlyBench.py
index 0194456d..f48e778c 100644
--- a/src/python/nightlyBench.py
+++ b/src/python/nightlyBench.py
@@ -725,7 +725,7 @@ def run():
       os.mkdir(subDirName)
       print(f"  {subDirName}")
       # TODO: optimize to single shared copy!
-      shutil.copy("/usr/share/gnuplot/6.0/js/gnuplot_svg.js", subDirName)
+      shutil.copy(f"{constants.BENCH_BASE_DIR}/src/javascript/gnuplot_svg.js", subDirName)
       shutil.copy(f"{constants.BENCH_BASE_DIR}/src/vmstat/index.html.template", f"{subDirName}/index.html")
       subprocess.check_call(f"gnuplot -c {constants.BENCH_BASE_DIR}/src/vmstat/vmstat.gpi {vmstatLogFileName} {prefix}", shell=True)


```

The problem though is that we also need gnuplot command itself

Didn’t work for me:

```
sudo yum install gnuplot
```

because the repo only has gnuplot 4.6 which doesn’t support interactive CSV

so installing from sources


```
cd /tmp
wget https://sourceforge.net/projects/gnuplot/files/gnuplot/6.0.4/gnuplot-6.0.4.tar.gz
tar -xzf  gnuplot-6.0.4.tar.gz
cd gnuplot-6.0.4
./configure --prefix=$HOME/local --without-x --without-cairo
make -j4
make install

### fix path
export PATH=$HOME/local/bin:$PATH
echo 'export PATH=$HOME/local/bin:$PATH' >> ~/.zshrc

### Make sure it has -c option !!!
gnuplot -h

```

### Gnuplot x range is invalid

Stacktrace

```
Traceback (most recent call last):
  File "./util/src/python/nightlyBench.py", line 2095, in <module>
    run()
  File "./util/src/python/nightlyBench.py", line 730, in run
    subprocess.check_call(f"gnuplot -c {constants.BENCH_BASE_DIR}/src/vmstat/vmstat.gpi {vmstatLogFileName} {prefix}", shell=True)
  File "/local/home/epotyom/.local/share/mise/installs/python/3.12.12/lib/python3.12/subprocess.py", line 413, in check_call
    raise CalledProcessError(retcode, cmd)
subprocess.CalledProcessError: Command 'gnuplot -c ./util/src/vmstat/vmstat.gpi ./logs/2026.01.07.11.48.33/fastIndexBigDocs.vmstat.log fastIndexBigDocs' returned non-zero exit status 1.
Traceback (most recent call last):
  File "./util/src/python/nightlyBench.py", line 2095, in <module>
    run()
  File "./util/src/python/nightlyBench.py", line 730, in run
    subprocess.check_call(f"gnuplot -c {constants.BENCH_BASE_DIR}/src/vmstat/vmstat.gpi {vmstatLogFileName} {prefix}", shell=True)
  File "/local/home/epotyom/.local/share/mise/installs/python/3.12.12/lib/python3.12/subprocess.py", line 413, in check_call
    raise CalledProcessError(retcode, cmd)
subprocess.CalledProcessError: Command 'gnuplot -c ./util/src/vmstat/vmstat.gpi ./logs/2026.01.07.11.48.33/fastIndexBigDocs.vmstat.log fastIndexBigDocs' returned non-zero exit status 1.
```

Getting more details

```
cd ../reports.nightly/2026.01.07.11.48.33
gnuplot -c ./util/src/vmstat/vmstat.gpi ./logs/2026.01.07.11.48.33/fastIndexBigDocs.vmstat.log fastIndexBigDocs

"./util/src/vmstat/vmstat.gpi" line 46: warning: Skipping data file with no valid points
"./util/src/vmstat/vmstat.gpi" line 46: warning: Skipping data file with no valid points
"./util/src/vmstat/vmstat.gpi" line 46: warning: Skipping data file with no valid points

plot vmstat using 19 : ($1+$2) title 'total' smooth csplines with filledcurves y1=0,      vmstat using 19 : 1 title 'runnable' smooth csplines with filledcurves y1=0,      vmstat using 19 : 2 title 'iowait' smooth csplines with filledcurves y1=0
                                                                                                                                                                                                                                                     ^
"./util/src/vmstat/vmstat.gpi" line 46: x range is invalid
```

looking at vmstats file


```
procs -----------------------memory---------------------- ---swap-- -----io---- -system-- --------cpu-------- -----timestamp-----
 r  b         swpd         free        inact       active   si   so    bi    bo   in   cs  us  sy  id  wa  st                 UTC
 5  0            0        68761        24058        91714    0    0    17   119    0    0   3   0  97   0   0 2026-01-08 08:32:42
 1  0            0        68626        24199        91714    0    0     8     0 6552 55355   8   1  92   0   0 2026-01-08 08:32:43
 1  0            0        68496        24329        91714    0    0     0   200 3065 34146   4   0  96   0   0 2026-01-08 08:32:44

```

Fix:

TBH not sure what is going on, column 19 seems to be correct - it is time; but I’ve changed it to column 18 and now it works and shows time as expected... Not sure what happened, maybe column starts at 0 now? Does it mean we have to change other columnts as well??? For now I’ve just changed to 18 all lines, for example (there are more lines below that also has to be changed)

```
diff --git a/src/vmstat/vmstat.gpi b/src/vmstat/vmstat.gpi
index 8751b4da..a6da1d2a 100644
--- a/src/vmstat/vmstat.gpi
+++ b/src/vmstat/vmstat.gpi
@@ -41,46 +41,46 @@ vmstat = "< grep -v r ". ARG1
 set title "Running Processes"
 set output ARG2 . "/processes.svg"
 set ylabel "Processes"
-plot vmstat using 19 : ($1+$2) title 'total' smooth csplines with filledcurves y1=0, \
-     vmstat using 19 : 1 title 'runnable' smooth csplines with filledcurves y1=0, \
-     vmstat using 19 : 2 title 'iowait' smooth csplines with filledcurves y1=0
+plot vmstat using 18 : ($1+$2) title 'total' smooth csplines with filledcurves y1=0, \
+     vmstat using 18 : 1 title 'runnable' smooth csplines with filledcurves y1=0, \
+     vmstat using 18 : 2 title 'iowait' smooth csplines with filledcurves y1=0
```

### Blunders

Stacktrace


```
Traceback (most recent call last):
  File "./util/src/python/nightlyBench.py", line 2095, in <module>
    run()
  File "./util/src/python/nightlyBench.py", line 839, in run
    blunders.upload(
  File "./util/src/python/blunders.py", line 36, in upload
    if constants.BLUNDER_ACCESS_KEY is None:
       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AttributeError: module 'constants' has no attribute 'BLUNDER_ACCESS_KEY'
```

Fix:

The long term fix would be to get access key I suppose, but at this point I just want to finish the run - I’m so close! I suppose running it with DEBUG=False would disable it, but there might be some other changes and consequences from using it, so I’m going with


```
diff --git a/src/python/nightlyBench.py b/src/python/nightlyBench.py
index f48e778c..ea6958e6 100644
--- a/src/python/nightlyBench.py
+++ b/src/python/nightlyBench.py
@@ -834,7 +834,7 @@ def run():
     w("</pre>")
     w("</html>\n")

-    if not DEBUG and REAL:
+    if False:
       # Blunders upload:
       blunders.upload(

```

### WiP

Stacktrace

```
Traceback (most recent call last):
  File "./util/src/python/nightlyBench.py", line 2127, in <module>
    run()
  File "./util/src/python/nightlyBench.py", line 366, in run
    lastRevs = findLastSuccessfulGitHashes()
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "./util/src/python/nightlyBench.py", line 1008, in findLastSuccessfulGitHashes
    raise RuntimeError(f"failed to determine last successful Lucene git hash from file {logFile}")
RuntimeError: failed to determine last successful Lucene git hash from file 2026.01.12.14.16.46.html
```

and also


```
Traceback (most recent call last):
  File "./util/src/python/nightlyBench.py", line 2127, in <module>
    run()
  File "./util/src/python/nightlyBench.py", line 366, in run
    lastRevs = findLastSuccessfulGitHashes()
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "./util/src/python/nightlyBench.py", line 1014, in findLastSuccessfulGitHashes
    raise RuntimeError(f"failed to determine last successful luceneutil git hash from file {logFile}")
RuntimeError: failed to determine last successful luceneutil git hash from file 2026.01.12.14.16.46.html
```

Fix
The `Lucene/Solr trunk rev...` line as well as luceneutil revision are only seem to be written if there was previous successful run, so if you are running nightlies second time you get this error.

I’ve just added following lines to the report

```
<html>
<h1>Mon 01/12/2026</h1>WARNING: Using incubator modules: jdk.incubator.vector
**Lucene/Solr trunk rev 367551036dd4c684d0999df44e517a9bb91c5026 ()
luceneutil revision 1e85f67fbde25a8057c2eff5f68980a68127c02c ()**
```

but the long term fix should be to always write hashes for successful run (TODO)

### Run is successful, but there are no graphs

See [dygraph-combined-dev.js](https://quip-amazon.com/Zs8EAuGbj42y#temp:C:VaIf2e2de0a9a2d46a693b8aabe4)


### JVM

Stacktrace


```
Traceback (most recent call last):
  File "./util/src/python/nightlyBench.py", line 2172, in <module>
    run()
  File "./util/src/python/nightlyBench.py", line 749, in run
    searchResults, cmpSearchDiffs, searchHeaps = r.simpleReport(resultsSearchPrev, resultsSearchNow, False, True, "prev", "now", writer=output.append)
                                                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "./util/src/python/benchUtil.py", line 1407, in simpleReport
    cmpDiffs = compareHits(baseRawResults, cmpRawResults, self.verifyScores, self.verifyCounts)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "./util/src/python/benchUtil.py", line 1859, in compareHits
    d1 = tasksToMap(r1, verifyScores, verifyCounts)
         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "./util/src/python/benchUtil.py", line 1835, in tasksToMap
    raise RuntimeError(f"ERROR: tasks differ from one iteration to the next: task={task} in JVM {run_iter} is missing from JVM 0")
RuntimeError: ERROR: tasks differ from one iteration to the next: task=body:names [facet_request=[FacetTask{dimension='Date.taxonomy'}]] in JVM 2 is missing from JVM 0
```

Fix: after changing JVM count, you should remove old *prev logs


```
rm ~/ws/upstream_lucene/logs/*.prev
```

### Misc

I logged some stacktraces I fixed before, unfortunately I’ve never written down most of them, and never mentioned how I fixed them - the fix must be somewhere in the code branch though.

```
NoSuchFileException: /Users/egor/workspace/lucene/data/enwiki-20120502-lines-1k-mpnet.vec

/Users/egor/workspace/lucene/util/../data/enwiki-20120502-mpnet.vec
```

```
less ../nightly_logs/2025.07.23.23.43.12/nrt.log

Exception in thread "Thread-3" Exception in thread "Thread-5" java.lang.RuntimeException: java.util.concurrent.ExecutionException: java.lang.IllegalStateException: Task cannot be reused
        at perf.TaskThreads$TaskThread.run(TaskThreads.java:137)
Caused by: java.util.concurrent.ExecutionException: java.lang.IllegalStateException: Task cannot be reused
        at java.base/java.util.concurrent.FutureTask.report(FutureTask.java:124)
        at java.base/java.util.concurrent.FutureTask.get(FutureTask.java:193)
        at perf.TaskThreads$TaskThread.run(TaskThreads.java:132)


/opt/homebrew/opt/openjdk@24//bin/java -server -Xms2g -Xmx4g --add-modules jdk.incubator.vector -XX:+HeapDumpOnOutOfMemoryError -XX:+UseParallelGC -classpath "/Users/egor/workspace/lucene/trunk.nightly/lucene/core/build/libs/lucene-core-11.0.0-SNAPSHOT.jar:/Users/egor/workspace/lucene/trunk.nightly/lucene/sandbox/build/classes/java/main:/Users/egor/workspace/lucene/trunk.nightly/lucene/misc/build/classes/java/main:/Users/egor/workspace/lucene/trunk.nightly/lucene/facet/build/classes/java/main:/Users/egor/workspace/lucene/trunk.nightly/lucene/analysis/common/build/classes/java/main:/Users/egor/workspace/lucene/trunk.nightly/lucene/analysis/icu/build/classes/java/main:/Users/egor/workspace/lucene/trunk.nightly/lucene/queryparser/build/classes/java/main:/Users/egor/workspace/lucene/trunk.nightly/lucene/grouping/build/classes/java/main:/Users/egor/workspace/lucene/trunk.nightly/lucene/suggest/build/classes/java/main:/Users/egor/workspace/lucene/trunk.nightly/lucene/highlighter/build/classes/java/main:/Users/egor/workspace/lucene/trunk.nightly/lucene/codecs/build/classes/java/main:/Users/egor/workspace/lucene/trunk.nightly/lucene/queries/build/classes/java/main:/Users/egor/workspace/lucene/trunk.nightly/lucene/join/build/classes/java/main:/Users/egor/workspace/lucene/trunk.nightly/lucene/spatial3d/build/classes/java/main:/Users/egor/workspace/lucene/util/lib/HdrHistogram.jar:/Users/egor/workspace/lucene/util/src/main/build/classes/java/main:/Users/egor/workspace/lucene/util/build" -ea org.apache.lucene.index.CheckIndex -threadCount 16 -level 2 "/Users/egor/workspace/lucene/indices/wikimedium.trunk.nightly.Lucene103.dvfields.nd27.625M/index" > /Users/egor/workspace/lucene/nightly_logs/2025.07.23.23.43.12/checkIndex.nrtIndexMediumDocs.log 2>&1


/opt/homebrew/opt/openjdk@24//bin/java -server -Xms2g -Xmx4g --add-modules jdk.incubator.vector -XX:+HeapDumpOnOutOfMemoryError -XX:+UseParallelGC -classpath "/Users/egor/workspace/lucene/trunk.nightly/lucene/core/build/libs/lucene-core-11.0.0-SNAPSHOT.jar:/Users/egor/workspace/lucene/trunk.nightly/lucene/sandbox/build/classes/java/main:/Users/egor/workspace/lucene/trunk.nightly/lucene/misc/build/classes/java/main:/Users/egor/workspace/lucene/trunk.nightly/lucene/facet/build/classes/java/main:/Users/egor/workspace/lucene/trunk.nightly/lucene/analysis/common/build/classes/java/main:/Users/egor/workspace/lucene/trunk.nightly/lucene/analysis/icu/build/classes/java/main:/Users/egor/workspace/lucene/trunk.nightly/lucene/queryparser/build/classes/java/main:/Users/egor/workspace/lucene/trunk.nightly/lucene/grouping/build/classes/java/main:/Users/egor/workspace/lucene/trunk.nightly/lucene/suggest/build/classes/java/main:/Users/egor/workspace/lucene/trunk.nightly/lucene/highlighter/build/classes/java/main:/Users/egor/workspace/lucene/trunk.nightly/lucene/codecs/build/classes/java/main:/Users/egor/workspace/lucene/trunk.nightly/lucene/queries/build/classes/java/main:/Users/egor/workspace/lucene/trunk.nightly/lucene/join/build/classes/java/main:/Users/egor/workspace/lucene/trunk.nightly/lucene/spatial3d/build/classes/java/main:/Users/egor/workspace/lucene/util/lib/HdrHistogram.jar:/Users/egor/workspace/lucene/util/src/main/build/classes/java/main:/Users/egor/workspace/lucene/util/build" perf.NRTPerfTest MMapDirectory "/Users/egor/workspace/lucene/indices/wikimedium.trunk.nightly.Lucene103.dvfields.nd27.625M/index" multi "/Users/egor/workspace/lucene/data/enwiki-20120502-lines-1k-fixed-utf8-with-random-label.txt" 17 1103 1800 4 1 1 update 5 no 0.0 body10.tasks
```
