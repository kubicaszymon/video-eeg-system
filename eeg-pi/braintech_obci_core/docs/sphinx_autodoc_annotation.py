
import inspect

from sphinx.ext.autodoc import FunctionDocumenter, MethodDocumenter, ClassDocumenter


def get_typing_link(obj):
    if obj.__qualname__ == 'Union':
        return ' or '.join(':class:`~{}.{}`'.format(p.__module__, p.__qualname__)
                           for p in obj.__union_params__)
    else:
        fullname = '%s.%s' % (obj.__module__, obj.__qualname__)
        return ':class:`~%s`' % fullname


def get_link(obj):
    if obj is None or obj == inspect.Signature.empty:
        return None
    elif inspect.ismodule(obj):
        return ':mod:`~{}`'.format(obj.__module__)
    elif inspect.isclass(obj):
        if obj.__module__ == 'builtins':
            return ":class:`%s`" % obj.__qualname__
        elif obj.__module__ == 'typing':
            return get_typing_link(obj)
        else:
            return ':class:`~%s.%s`' % (obj.__module__, obj.__qualname__)
    elif inspect.isfunction(obj):
        return ':func:`~%s.%s`' % (obj.__module__, obj.__qualname__)
    else:
        return None


def get_param_type(param):
    if param.annotation != inspect.Signature.empty:
        return param.annotation
    elif isinstance(param.default, (bool, int, float, str, bytes)):
        # We don't want to overreach ourselves. Too many possibilities of
        # messing up. So, we only support basic types here.
        return type(param.default)
    else:
        return None


def add_annotation_content(obj, result):  # noqa: C901
    try:
        sig = inspect.signature(obj)
    except ValueError:
        # Can't extract signature, do nothing
        return

    existing_contents = ''.join(result)
    toadd = []
    for param in sig.parameters.values():
        type_directive = ':type %s:' % param.name
        if type_directive in existing_contents:
            # We already specify the type of that argument in the docstring,
            # don't specify it again.
            continue
        arg_link = get_link(get_param_type(param))
        if arg_link:
            toadd.append('{} {}'.format(type_directive, arg_link))

    if ':rtype:' not in existing_contents:
        return_link = get_link(sig.return_annotation)
        if return_link:
            toadd.append(':rtype: {}'.format(return_link))

    if toadd:
        # Let's see where we're going to insert our directives. We can't append
        # it at the end of the docstring because there might be a section
        # breaker between our params and the end of the list that will also
        # break our :type: stuff. We have to try to keep them grouped.
        for i, s in enumerate(result):
            if ':param' in s:
                insert_index = i
                break
        else:
            # We don't have a parameters directive, just add nothing.
            return
        for line in toadd:
            # Yeah, inefficient, but we need to keep the same list instance.
            result.insert(insert_index, line)


def generate_documenter(BaseClass):
    class MyDocumenter(BaseClass):
        def get_doc(self, *args, **kwargs):
            result = super().get_doc(*args, **kwargs)
            if result:
                add_annotation_content(self.object, result[-1])
            return result
    return MyDocumenter


def setup(app):
    for DocumenterClass in (FunctionDocumenter,
                            MethodDocumenter,
                            ClassDocumenter):
        app.add_autodocumenter(generate_documenter(DocumenterClass))
