import datetime
import pickle
import os
import re

CHANGES = [
  ('2016-10-04',
   'LUCENE-7474: Doc values writers should use sparse encoding'),
  ('2016-10-17',
   'LUCENE-7489: Better sparsity support for Lucene70DocValuesFormat'),
  ('2016-10-18',
   'LUCENE-7501: Save one heap byte per index node in the dimensional points index for the 1D case'),
  ('2016-10-24 08:51:23',
   'LUCENE-7462: Give doc values an advanceExact method')
  ]

reMergeTime = re.compile(r': (\d+) msec to merge ([a-z ]+) \[(\d+) docs\]')
reFlushTime = re.compile(r': flush time ([.0-9]+) msec')
reDocsPerMB = re.compile('newFlushedSize.*? docs/MB=([.,0-9]+)$')
reIndexingRate = re.compile('([.0-9]+) sec: (\d+) docs; ([.0-9]+) docs/sec; ([.0-9]+) MB/sec')
        
def extractIndexStats(indexLog):
  mergeTimesSec = {}
  flushTimeSec = 0
  docsPerMB = 0
  flushCount = 0
  lastDPSMatch = None
  with open(indexLog, 'r', encoding='utf-8') as f:
    while True:
      line = f.readline()
      if line == '':
        break
      line = line.strip()
      m = reMergeTime.search(line)
      if m is not None:
        msec, part, docCount = m.groups()
        msec = int(msec)
        docCount = int(docCount)
        if part not in mergeTimesSec:
          mergeTimesSec[part] = [0, 0]
        l = mergeTimesSec[part]
        l[0] += msec/1000.0
        l[1] += docCount
      m = reFlushTime.search(line)
      if m is not None:
        flushTimeSec += float(m.group(1))/1000.
      m = reDocsPerMB.search(line)
      if m is not None:
        docsPerMB += float(m.group(1).replace(',', ''))
        flushCount += 1
      m = reIndexingRate.search(line)
      if m is not None:
        lastDPSMatch = m
      
  return float(lastDPSMatch.group(3)), mergeTimesSec, flushTimeSec, docsPerMB/flushCount

def msecToQPS(x):
  return 1000./x

reHits = re.compile('T(.) (.*?) sort=(.*?): ([0-9]+) hits in ([.0-9]+) msec')
def extractSearchStats(searchLog):
  
  heapBytes = None
  byThread = {}
  
  with open(searchLog, 'r', encoding='utf-8') as f:
    while True:
      line = f.readline()
      if line == '':
        break
      line = line.strip()
      if line.startswith('HEAP: '):
        heapBytes = int(line[6:])
      else:
        m = reHits.match(line)
        if m is not None:
          threadID, queryDesc, sortDesc, hitCount, msec = m.groups()
          if threadID not in byThread:
            byThread[threadID] = []
          if sortDesc == 'null':
            sortDesc = None
          else:
            sortDesc = 'longitude'
          byThread[threadID].append((queryDesc, sortDesc, int(hitCount), float(msec)))

  byQuerySort = {}
  for threadID, results in byThread.items():
    # discard warmup
    results = results[10:]
    for queryDesc, sortDesc, hitCount, msec in results:
      tup = (queryDesc, sortDesc)
      if tup not in byQuerySort:
        byQuerySort[tup] = []
      byQuerySort[tup].append(msec)

  allResults = [heapBytes]
  # TODO: also "both colors" (all docs) and "latitude point range"
  for key in (('cab_color:g', None),
              ('cab_color:g', 'longitude'),
              ('cab_color:y', None),
              ('cab_color:y', 'longitude'),
              ('cab_color:y cab_color:g', None)):
    l = byQuerySort[key]
    l.sort()
    # median result:
    allResults.append(l[len(l)//2])

  key1 = ('green_pickup_latitude:[40.75 TO 40.9] yellow_pickup_latitude:[40.75 TO 40.9]', None)
  key2 = ('pickup_latitude:[40.75 TO 40.9]', None)
  if key1 in byQuerySort:
    l = byQuerySort[key1]
  else:
    l = byQuerySort[key2]

  l.sort()
  # median result:
  allResults.append(l[len(l)//2])

  # heap, green-no-sort, green-longitude-sort, yellow-no-sort, yellow-longitude-sort
  return tuple(allResults)

def toGB(x):
  return x/1024./1024./1024.

def toMB(x):
  return x/1024./1024.

def toDateTime(parts):
  parts = (int(x) for x in parts)
  return datetime.datetime(*parts)

reDateTime = re.compile(r'(\d\d\d\d)\.(\d\d)\.(\d\d)\.(\d\d)\.(\d\d)\.(\d\d)')

def toMSEpoch(dt):
  epoch = datetime.datetime.utcfromtimestamp(0)
  return 1000. * (dt - epoch).total_seconds()
  
def main():

  global dateWindow
  
  allResults = []

  l = os.listdir('/l/logs.nightly/taxis')
  l.sort()

  indexSizeData = []
  indexDPSData = []
  checkIndexTimeData = []
  flushTimesData = []
  searcherHeapMBData = []
  searchSortQPSData = []
  searchQPSData = []
  searchBQQPSData = []
  searchRangeQPSData = []
  docsPerMBData = []
  dvMergeTimesData = []
  gitHashes = []
  
  for fileName in l:
    if os.path.exists('/l/logs.nightly/taxis/%s/results.pk' % fileName):
      results = pickle.loads(open('/l/logs.nightly/taxis/%s/results.pk' % fileName, 'rb').read())

      # load results written directly by the benchmarker:
      luceneRev, nonSparseDiskBytes, sparseDiskBytes, nonSparseCheckIndexTimeSec, sparseCheckIndexTimeSec = results

      gitHashes.append(luceneRev)

      # parse logs for more details results:
      logResultsFileName = '/l/logs.nightly/taxis/%s/logResults.pk' % fileName
      if os.path.exists(logResultsFileName):
        sparseIndexStats, nonSparseIndexStats, sparseSearchStats, nonSparseSearchStats = pickle.loads(open(logResultsFileName, 'rb').read())
      else:
        sparseIndexStats = extractIndexStats('/l/logs.nightly/taxis/%s/index.1threads.sparse.log' % fileName)
        nonSparseIndexStats = extractIndexStats('/l/logs.nightly/taxis/%s/index.1threads.nonsparse.log' % fileName)

        sparseSearchStats = extractSearchStats('/l/logs.nightly/taxis/%s/searchSparse.log' % fileName)
        nonSparseSearchStats = extractSearchStats('/l/logs.nightly/taxis/%s/searchNonSparse.log' % fileName)
        open(logResultsFileName, 'wb').write(pickle.dumps((sparseIndexStats, nonSparseIndexStats, sparseSearchStats, nonSparseSearchStats)))
                                             
      m = reDateTime.match(fileName)

      indexSizeData.append((m.groups(), toGB(nonSparseDiskBytes), toGB(sparseDiskBytes)))
      indexDPSData.append((m.groups(), nonSparseIndexStats[0]/1000., sparseIndexStats[0]/1000.))
      checkIndexTimeData.append((m.groups(), nonSparseCheckIndexTimeSec, sparseCheckIndexTimeSec))
      flushTimesData.append((m.groups(), nonSparseIndexStats[2], sparseIndexStats[2]))
      searcherHeapMBData.append((m.groups(), toMB(nonSparseSearchStats[0]), toMB(sparseSearchStats[0])))
      searchSortQPSData.append((m.groups(),
                                msecToQPS(nonSparseSearchStats[2]),
                                msecToQPS(sparseSearchStats[2]),
                                msecToQPS(nonSparseSearchStats[4]),
                                msecToQPS(sparseSearchStats[4])))
      searchQPSData.append((m.groups(),
                            msecToQPS(nonSparseSearchStats[1]),
                            msecToQPS(sparseSearchStats[1]),
                            msecToQPS(nonSparseSearchStats[3]),
                            msecToQPS(sparseSearchStats[3])))
      searchBQQPSData.append((m.groups(),
                              msecToQPS(nonSparseSearchStats[5]),
                              msecToQPS(sparseSearchStats[5])))
      searchRangeQPSData.append((m.groups(),
                                 msecToQPS(nonSparseSearchStats[6]),
                                 msecToQPS(sparseSearchStats[6])))
      docsPerMBData.append((m.groups(), nonSparseIndexStats[3]/1000., sparseIndexStats[3]/1000.))
      dvMergeTimesData.append((m.groups(), nonSparseIndexStats[1]['doc values'][0], sparseIndexStats[1]['doc values'][0]))

      allResults.append((m.groups(),
                         nonSparseDiskBytes,
                         sparseDiskBytes,
                         nonSparseCheckIndexTimeSec,
                         sparseCheckIndexTimeSec) +
                        nonSparseIndexStats +
                        sparseIndexStats +
                        nonSparseSearchStats +
                        sparseSearchStats)

  # attach each known change to the next datapoint after that change's timestamp:
  lastDateTime = None
  for i in range(len(CHANGES)):
    x = CHANGES[i][0].split()
    x1 = tuple(int(y) for y in x[0].split('-'))
    if len(x) == 1:
      x1 += (0, 0, 0)
    else:
      x1 += tuple(int(y) for y in x[1].split(':'))

    changeDateTime = datetime.datetime(*x1)
      
    for tup in allResults:
      pointDateTime = datetime.datetime(*(int(x) for x in tup[0]))
      if lastDateTime is not None and pointDateTime > changeDateTime:
        CHANGES[i] += ('%s-%s-%s %s:%s:%s' % tup[0],)
        #print('%s -> %s' % (CHANGES[i][0], CHANGES[i][2]))
        break
      lastDateTime = pointDateTime
      
  startDateTime = toDateTime(indexSizeData[0][0])
  endDateTime = toDateTime(indexSizeData[-1][0])
  sixHours = datetime.timedelta(hours=6)

  # This way it's clear we are seeing the whole date range:
  dateWindow = (toMSEpoch(startDateTime - sixHours), toMSEpoch(endDateTime + sixHours))

  with open('/x/tmp/sparseResults.html', 'w') as f:
    f.write('''
<html>
<head>
<script type="text/javascript" src="dygraph-combined-dev.js"></script>
<script type="text/javascript">
''')
    f.write('gitHashes = %s;\n' % repr(gitHashes))
    f.write('''
function onPointClick(e, p) {
  if (p.idx > 0) {
    top.location = "https://github.com/apache/lucene-solr/compare/" + gitHashes[p.idx-1] + "..." + gitHashes[p.idx];
  } else {
    top.location = "https://github.com/apache/lucene-solr/commit/" + gitHashes[p.idx];
  }
}
</script>
<style type="text/css">
a:hover * {
  text-decoration: underline;
}

html * {
  #font-size: 1em !important;
  text-decoration: none;
  #color: #000 !important;
  font-family: Verdana !important;
}

.dygraph-legend > span.highlight { border: 1px solid grey}

.dygraph-legend > span.highlight { display: inline; }
</style>
</head>
<body>
''')

    writeOneGraph(f, indexSizeData, 'index_size', 'Index size (GB)')
    writeOneGraph(f, indexDPSData, 'index_throughput', 'Indexing rate 1 thread (K docs/sec)')
    writeOneGraph(f, docsPerMBData, 'index_docs_per_mb', 'Docs per MB RAM at flush (K docs)')
    writeOneGraph(f, checkIndexTimeData, 'check_index_time', 'CheckIndex time (sec)')
    writeOneGraph(f, flushTimesData, 'flush_times', 'New segment flush time (sec)')
    writeOneGraph(f, dvMergeTimesData, 'dv_merge_times', 'Doc values merge time (sec)')
    writeOneGraph(f, searcherHeapMBData, 'searcher_heap', 'Searcher heap used (MB)')
    writeOneGraph(f, searchSortQPSData, 'search_sort_qps', 'TermQuery, sort by longitude (QPS)',
                  ('Date', 'Green cab (non-sparse)', 'Green cab (sparse)', 'Yellow cab (non-sparse)', 'Yellow cab (sparse)'))
    writeOneGraph(f, searchQPSData, 'search_qps', 'TermQuery (QPS)',
                  ('Date', 'Green cab (non-sparse)', 'Green cab (sparse)', 'Yellow cab (non-sparse)', 'Yellow cab (sparse)'))
    writeOneGraph(f, searchBQQPSData, 'search_bq_qps', 'BooleanQuery SHOULD + SHOULD (QPS)')
    writeOneGraph(f, searchRangeQPSData, 'search_range_qps', 'Pickup latitude range (QPS)')

    f.write('</body>\n</html>\n')

topPct = 5

def getLabel(label):
  if label < 26:
    s = chr(65+label)
  else:
    s = '%s%s' % (chr(65+(label//26 - 1)), chr(65 + (label%26)))
  return s

def writeOneGraph(f, data, id, title, headers=None):
  global topPct
  
  f.write('''
<style type="text/css">
#%s {
  position: absolute;
  left: 10px;
  top: %d%%;
}
</style>
''' % (id, topPct))

  topPct += 75

  if headers is None:
    headers = ['Date', 'Non-sparse', 'Sparse']

  f.write('''
<div id="%s" style="height:70%%; width:95%%"></div>
<script type="text/javascript">
  g = new Dygraph(

  // containing div
  document.getElementById("%s"),
  "%s\\n"
''' % (id, id, ','.join(headers)))

  maxValue = None

  for timestamp, *values in data:
    f.write('  + "%s-%s-%s %s:%s:%s' % timestamp)
    f.write(',%s\\n"\n' % ','.join([str(x) for x in values]))
    for x in values:
      if type(x) is float:
        if maxValue is None or x > maxValue:
          maxValue = x

  if id in ('search_qps', 'search_sort_qps'):
    # fix the value axis so the legend doesn't obscure the series:
    otherOptions = '    "valueRange": [0.0, %s],' % int(maxValue+3)
  else:
    otherOptions = ''
  

  f.write('''
  , { "title": "<a href=\'#%s\'><font size=+2>%s</font></a>",
    // "colors": ["#DD1E2F", "#EBB035", "#06A2CB", "#218559", "#B0A691", "#192823"],
    "colors": ["#00BFB3", "#FED10A", "#0078A0", "#DF4998", "#93C90E", "#00A9E5", "#222", "#AAA", "#777"],
    "drawGapEdgePoints": true,
    "xlabel": "Date",
    "ylabel": "%s",
    "pointClickCallback": onPointClick,
    //"labelsDivWidth": 500,
    "labelsSeparateLines": true,
    "pointSize": 3,
    "gridLineColor": "#BBB",
    "colorSaturation": 0.5,
    "highlightCircleSize": 5,
    "strokeWidth": 2.0,
    "connectSeparatedPoints": true,
    "drawPoints": true,
    "includeZero": true,
    "axisLabelColor": "#555",
    "axisLineColor": "#555",
    "dateWindow": [%s, %s],
    highlightSeriesOpts: {
      strokeWidth: 3,
      strokeBorderWidth: 1,
      highlightCircleSize: 5
    },
    %s
  });
  ''' % (id, title, title, dateWindow[0], dateWindow[1], otherOptions))

  f.write('g.ready(function() {g.setAnnotations([')
  for i in range(len(CHANGES)):
    change = CHANGES[i]
    if len(change) == 3:
      timeStamp = change[2]
      f.write('{series: "%s", x: "%s", shortText: "%s", text: "%s"},\n' % \
              (headers[2], timeStamp, getLabel(i), change[1].replace('"', '\\"')))
  f.write(']);});\n')

  f.write('</script>\n')

if __name__ == '__main__':
  main()