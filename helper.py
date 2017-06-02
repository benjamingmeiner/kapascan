"""
Helper functions, not fitting into the other modules.
"""


class cached_property(object):
    """
    Descriptor (non-data) for building an attribute on-demand on first use.
    """
    def __init__(self, factory):
        """
        <factory> is called such: factory(instance) to build the attribute.
        """
        self._attr_name = factory.__name__
        self._factory = factory

    def __get__(self, instance, owner):
        # Build the attribute.
        attr = self._factory(instance)

        # Cache the value; hide ourselves.
        setattr(instance, self._attr_name, attr)

        return attr


def query_yes_no(question, default="yes"):
    """
    Asks a yes/no question via input() and returns the answer.

    Parameters
    ----------
    question : str
        The string that is presented to the user.

    default : str {"yes", "no"}, optional
        The presumed answer if the user just hits <Enter>.

    Returns
    -------
    answer : bool
        True for "yes" or False for "no".
    """
    valid = {"yes": True, "y": True, "ye": True, "no": False, "n": False}
    if default is None:
        prompt = " [y/n] "
    elif default == "yes":
        prompt = " [Y/n] "
    elif default == "no":
        prompt = " [y/N] "
    else:
        raise ValueError("invalid default answer: '%s'" % default)
    while True:
        print(question + prompt, end='')
        choice = input("--->  ").lower()
        if default is not None and choice == '':
            return valid[default]
        elif choice in valid:
            return valid[choice]
        else:
            print("Please respond with 'yes' or 'no' (or 'y' or 'n').")


def query_options(options, default=None):
    for i, line in enumerate(options):
        print("{} [{}] {}".format("-" if i + 1 == default else " ", i + 1, line))
    while True:
        choice = input("--->  ")
        if default is not None and choice == '':
            try:
                return int(default)
            except ValueError:
                raise ValueError("Default option {} can not be casted to int".format(default))
        else:
            try:
                number = int(choice)
            except ValueError:
                print("Please enter an interger in range 1-{}!".format(len(options)))
                continue
            if 0 < number < len(options) + 1:
                return number
            else:
                print("Please enter an interger in range 1-{}!".format(len(options)))
