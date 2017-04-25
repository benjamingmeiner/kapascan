"""helper functions, not fitting into the other modules."""


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
