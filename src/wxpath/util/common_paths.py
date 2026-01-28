XPATH_BOOL_INTERNAL_LINKS = (
    "    not(starts-with(., 'http')) or "  # Relative links
    "    contains(., '://{0}') or "        # Root domain match
    "    contains(., '.{0}')"              # Subdomain match
)
XPATH_BOOL_EXTERNAL_LINKS = "not(" + XPATH_BOOL_INTERNAL_LINKS + ")"

# allows for false positives
XPATH_PATH_TO_INTERNAL_LINKS = "//a/@href[" + XPATH_BOOL_INTERNAL_LINKS + "]"
XPATH_PATH_TO_EXTERNAL_LINKS = "//a/@href[" + XPATH_BOOL_EXTERNAL_LINKS + "]" 

XPATH_PATH_TO_TEXT_NODE_PARENTS = '//body\
                        //*[not(\
                            self::script or \
                            self::noscript or \
                            self::style or \
                            self::i or \
                            self::b or \
                            self::strong or \
                            self::span or \
                            self::a)] \
                            /text()[string-length(normalize-space()) > 20]/..'
