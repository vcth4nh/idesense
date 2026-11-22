// Outline fixture: an export default object that does not start at line 1,
// with an array of object literals and a spread element over several lines.
// The structure view gives an object literal in an array no text.

export default {
    title: 'outline',
    fields: [
        { name: 'first', value: 1 },
        {
            name: 'second',
            value: 2,
        },
        ...(process.env.OUTLINE_EXTRA_FIELDS
            ? [
                  {
                      name: 'third',
                      value: 3,
                      inline: false,
                  },
              ]
            : []),
    ],
};
