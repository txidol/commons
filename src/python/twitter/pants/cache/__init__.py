import os
import urlparse
from twitter.pants.cache.pinger import Pinger
from twitter.pants.cache.combined_artifact_cache import CombinedArtifactCache
from twitter.pants.cache.local_artifact_cache import LocalArtifactCache
from twitter.pants.cache.restful_artifact_cache import RESTfulArtifactCache


def select_best_url(spec, pinger, log):
  urls = spec.split('|')
  if len(urls) == 1:
    return urls[0]  # No need to ping if we only have one option anyway.
  netlocs = map(lambda url: urlparse.urlparse(url)[1], urls)
  pingtimes = pinger.pings(netlocs)  # List of pairs (host, time in ms).
  log.debug('Artifact cache server ping times: %s' %
            ', '.join(['%s: %3f secs' % p for p in pingtimes]))
  argmin = min(xrange(len(pingtimes)), key=lambda i: pingtimes[i][1])
  best_url = urls[argmin]
  if pingtimes[argmin][1] == Pinger.UNREACHABLE:
    return None  # No reachable artifact caches.
  log.debug('Best artifact cache is %s' % best_url)
  return best_url


def create_artifact_cache(log, artifact_root, spec, task_name, local_readonly, remote_readonly):
  """Returns an artifact cache for the specified spec.

  spec can be:
    - a path to a file-based cache root.
    - a URL of a RESTful cache root.
    - a bar-separated list of URLs, where we'll pick the one with the best ping times.
    - A list of the above, for a combined cache.
  """
  if not spec:
    raise ValueError('Empty artifact cache spec')
  if isinstance(spec, basestring):
    if spec.startswith('/') or spec.startswith('~'):
      path = os.path.join(spec, task_name)
      log.info('%s using local artifact cache at %s' % (task_name, path))
      return LocalArtifactCache(log, artifact_root, path, read_only=local_readonly)
    elif spec.startswith('http://') or spec.startswith('https://'):
      # Caches are supposed to be close, and we don't want to waste time pinging on no-op builds.
      # So we ping twice with a short timeout.
      pinger = Pinger(timeout=0.5, tries=2)
      best_url = select_best_url(spec, pinger, log)
      if best_url:
        url = best_url.rstrip('/') + '/' + task_name
        log.info('%s using remote artifact cache at %s' % (task_name, url))
        return RESTfulArtifactCache(log, artifact_root, url, read_only=remote_readonly)
      else:
        log.warn('%s has no reachable artifact cache in %s.' % (task_name, spec))
        return None
    else:
      raise ValueError('Invalid artifact cache spec: %s' % spec)
  elif isinstance(spec, (list, tuple)):
    caches = filter(None, [ create_artifact_cache(log, artifact_root, x, task_name,
                                                  local_readonly, remote_readonly) for x in spec ])
    return CombinedArtifactCache(caches) if caches else None
