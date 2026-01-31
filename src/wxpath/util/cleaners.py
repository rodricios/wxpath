from collections import Counter

from wxpath.util.common_paths import XPATH_PATH_TO_TEXT_NODE_PARENTS


def main_text_extractor(element):
    """Inspired by my eatiht implementation:
    https://github.com/rodricios/eatiht
    """
    try:
        xpath_finder = element.getroot().getroottree().getpath
    except(AttributeError):
        xpath_finder = element.getroottree().getpath

    nodes_with_text = element.xpath(XPATH_PATH_TO_TEXT_NODE_PARENTS)

    sent_xpath_pairs = [
        # hard-code paragraph breaks (there has to be a better way)
        (n , xpath_finder(n))
        for n in nodes_with_text
    ]

    parent_paths = [p.rsplit('/', 1)[0] for s, p in sent_xpath_pairs]

    # build frequency distribution
    max_path = Counter(parent_paths).most_common()[0][0]

    article_text = ' '.join([''.join(s.xpath('.//text()')) 
                             for (s, x) in sent_xpath_pairs if max_path in x])

    return article_text
